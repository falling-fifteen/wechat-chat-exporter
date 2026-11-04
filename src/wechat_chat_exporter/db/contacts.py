"""Best-effort contact and session-name resolution."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ..model.session import Session

_USER_COLUMNS = ("user_name", "username", "wxid", "UserName")
_NAME_COLUMNS = ("remark", "nick_name", "nickname", "alias", "display_name", "nick")


def connect_ro(path: str | Path) -> sqlite3.Connection:
    uri = Path(path).resolve().as_uri() + "?mode=ro&immutable=1"
    con = sqlite3.connect(uri, uri=True)
    con.execute("PRAGMA query_only=ON")
    return con


def _tables(con: sqlite3.Connection) -> list[str]:
    return [row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]


def _columns(con: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in con.execute(f'PRAGMA table_info("{table}")')]


class ContactResolver:
    def __init__(self, session_db: Path | None, contact_db: Path | None):
        self.session_db = session_db
        self.contact_db = contact_db
        self._names: dict[str, str] | None = None

    def _load_names(self) -> dict[str, str]:
        if self._names is not None:
            return self._names
        names: dict[str, str] = {}
        if not self.contact_db or not self.contact_db.exists():
            self._names = names
            return names
        try:
            con = connect_ro(self.contact_db)
        except sqlite3.Error:
            self._names = names
            return names
        try:
            for table in _tables(con):
                cols = _columns(con, table)
                user_col = next((c for c in _USER_COLUMNS if c in cols), None)
                if not user_col:
                    continue
                name_col = next((c for c in _NAME_COLUMNS if c in cols), None)
                if not name_col:
                    continue
                try:
                    for user, name in con.execute(
                        f'SELECT "{user_col}", "{name_col}" FROM "{table}"'
                    ):
                        if user and name and str(name).strip():
                            key = str(user)
                            # Prefer remark-like columns; keep the first non-empty.
                            names.setdefault(key, str(name).strip())
                except sqlite3.Error:
                    continue
        finally:
            con.close()
        self._names = names
        return names

    def display_name(self, username: str) -> str:
        return self._load_names().get(username, "") or username

    def sessions(self) -> list[Session]:
        if not self.session_db or not self.session_db.exists():
            return []
        try:
            con = connect_ro(self.session_db)
        except sqlite3.Error:
            return []
        try:
            table = next(
                (t for t in _tables(con) if t.lower() == "sessiontable"),
                None,
            )
            if not table:
                return []
            cols = _columns(con, table)
            if "username" not in cols:
                return []
            order = "sort_timestamp" if "sort_timestamp" in cols else "username"
            summary = "summary" if "summary" in cols else "''"
            rows = con.execute(f'SELECT username, {order}, {summary} FROM "{table}"').fetchall()
        except sqlite3.Error:
            return []
        finally:
            con.close()

        out: list[Session] = []
        for username, last_ts, summary_text in rows:
            if not username:
                continue
            out.append(
                Session(
                    username=str(username),
                    display_name=self.display_name(str(username)),
                    last_timestamp=int(last_ts or 0),
                    summary=str(summary_text or ""),
                )
            )
        out.sort(key=lambda s: s.last_timestamp, reverse=True)
        return out
