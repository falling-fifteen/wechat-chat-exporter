"""Cross-shard message queries.

WeChat 4.x splits one logical conversation across ``message_*.db`` shards.
The same ``Msg_<md5(username)>`` table can exist in several shards.  The
reference DLL silently reads only one shard (hence the well-known 2400-message
cap); this repository reads every shard and merges the results.
"""

from __future__ import annotations

import hashlib
import heapq
import sqlite3
from collections.abc import Iterable, Iterator
from pathlib import Path

from ..errors import UnsupportedSchemaError
from ..model import local_type as lt
from ..model.message import Attachment, Message
from ..parse.content import parse_message_content
from .contacts import ContactResolver, connect_ro
from .decrypt import DecryptedLayout

_COLUMNS = (
    "local_id, server_id, local_type, sort_seq, real_sender_id, create_time, "
    "message_content, compress_content, packed_info_data"
)


def table_name(username: str) -> str:
    return "Msg_" + hashlib.md5(username.encode("utf-8")).hexdigest()


class MessageRepository:
    def __init__(
        self,
        decrypted: DecryptedLayout,
        me_wxid: str = "",
        contacts: ContactResolver | None = None,
        *,
        me_label: str = "我",
        system_label: str = "系统",
    ):
        self.decrypted = decrypted
        self.me_wxid = me_wxid
        self.contacts = contacts or ContactResolver(decrypted.session_db, decrypted.contact_db)
        self.me_label = me_label
        self.system_label = system_label

    def _table_exists(self, con: sqlite3.Connection, table: str) -> bool:
        return (
            con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            is not None
        )

    def _name_map(self, con: sqlite3.Connection) -> dict[int, str]:
        if not self._table_exists(con, "Name2Id"):
            return {}
        try:
            return {
                int(rowid): str(user)
                for rowid, user in con.execute("SELECT rowid, user_name FROM Name2Id")
            }
        except sqlite3.Error:
            return {}

    def count(self, username: str) -> int:
        table = table_name(username)
        total = 0
        for shard in self.decrypted.shards:
            try:
                con = connect_ro(shard)
            except sqlite3.Error:
                continue
            try:
                if self._table_exists(con, table):
                    total += int(con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            finally:
                con.close()
        return total

    def _row_to_message(
        self,
        row: tuple,
        names: dict[int, str],
    ) -> Message | None:
        (
            local_id,
            server_id,
            local_type,
            sort_seq,
            sender_id,
            create_time,
            content,
            compress,
            packed,
        ) = row
        parsed = parse_message_content(local_type, content, compress, packed)
        user = names.get(int(sender_id or 0), "")
        if user and self.me_wxid and user == self.me_wxid:
            sender = self.me_label
        elif user:
            sender = self.contacts.display_name(user) or user
        else:
            sender = self.system_label
        base, sub = lt.split_type(int(local_type or 0))
        attachment = None
        if base == lt.IMAGE:
            attachment = Attachment(
                kind="image",
                error="" if parsed.image_md5 else "no_md5",
                source_path=parsed.image_md5,
            )
        return Message(
            local_id=int(local_id or 0),
            server_id=int(server_id or 0),
            timestamp=int(create_time or 0),
            sort_seq=int(sort_seq or 0),
            sender_id=int(sender_id or 0),
            sender_name=sender,
            local_type=int(local_type or 0),
            base_type=base,
            sub_type=sub,
            kind=parsed.kind,
            text=parsed.text,
            attachment=attachment,
            extra={
                "image_md5": parsed.image_md5,
                "image_aeskey": parsed.image_aeskey,
            },
        )

    def _iter_shard(
        self,
        shard: Path,
        table: str,
        since: int | None,
        until: int | None,
        ascending: bool,
    ) -> Iterator[Message]:
        con = connect_ro(shard)
        try:
            if not self._table_exists(con, table):
                return
            names = self._name_map(con)
            clauses = []
            params: list[int] = []
            if since is not None:
                clauses.append("create_time >= ?")
                params.append(since)
            if until is not None:
                clauses.append("create_time <= ?")
                params.append(until)
            where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
            order = "ASC" if ascending else "DESC"
            sql = (
                f'SELECT {_COLUMNS} FROM "{table}"{where} '
                f"ORDER BY create_time {order}, sort_seq {order}, local_id {order}"
            )
            cur = con.execute(sql, params)
            for row in cur:
                msg = self._row_to_message(row, names)
                if msg is not None:
                    yield msg
        finally:
            con.close()

    def iter_messages(
        self,
        username: str,
        *,
        since: int | None = None,
        until: int | None = None,
        limit: int | None = None,
        ascending: bool = True,
        exclude_system: bool = False,
    ) -> Iterator[Message]:
        table = table_name(username)
        found = False
        for shard in self.decrypted.shards:
            con = connect_ro(shard)
            try:
                if self._table_exists(con, table):
                    found = True
                    break
            finally:
                con.close()
        if not found:
            raise UnsupportedSchemaError(f"没有找到会话表: {table}")

        if limit is not None:
            if limit <= 0:
                return
            per_shard: list[list[Message]] = []
            for shard in self.decrypted.shards:
                rows = []
                con = connect_ro(shard)
                try:
                    if not self._table_exists(con, table):
                        continue
                    names = self._name_map(con)
                    clauses = []
                    params: list[int] = []
                    if since is not None:
                        clauses.append("create_time >= ?")
                        params.append(since)
                    if until is not None:
                        clauses.append("create_time <= ?")
                        params.append(until)
                    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
                    sql = (
                        f'SELECT {_COLUMNS} FROM "{table}"{where} '
                        "ORDER BY create_time DESC, sort_seq DESC, local_id DESC LIMIT ?"
                    )
                    params.append(limit)
                    for row in con.execute(sql, params):
                        msg = self._row_to_message(row, names)
                        if msg is not None:
                            rows.append(msg)
                finally:
                    con.close()
                per_shard.append(rows)

            merged = heapq.merge(
                *per_shard,
                key=lambda m: (m.timestamp, m.sort_seq, m.local_id),
                reverse=True,
            )
            selected = list(merged)[:limit]
            if ascending:
                selected.reverse()
            yield from self._dedupe(selected, exclude_system)
            return

        generators = [
            self._iter_shard(shard, table, since, until, ascending)
            for shard in self.decrypted.shards
        ]
        merged = heapq.merge(
            *generators,
            key=lambda m: (m.timestamp, m.sort_seq, m.local_id),
        )
        yield from self._dedupe(merged, exclude_system)

    @staticmethod
    def _dedupe(messages: Iterable[Message], exclude_system: bool) -> Iterator[Message]:
        seen: set[int] = set()
        for msg in messages:
            if exclude_system and msg.base_type == lt.SYSTEM:
                continue
            if msg.server_id:
                if msg.server_id in seen:
                    continue
                seen.add(msg.server_id)
            yield msg
