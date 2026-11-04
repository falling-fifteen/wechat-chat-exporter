"""Locate the WeChat 4.x ``db_storage`` layout."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ..errors import UnsupportedSchemaError

_WXID = re.compile(r"^(wxid_[a-zA-Z0-9]+)(?:_[a-zA-Z0-9]+)?$")


@dataclass
class DataLayout:
    db_storage: Path
    shards: list[Path] = field(default_factory=list)
    session_db: Path | None = None
    contact_db: Path | None = None
    account_dir: Path | None = None
    account_wxid: str = ""
    attach_dir: Path | None = None
    wal_bytes: int = 0
    wal_files: list[str] = field(default_factory=list)

    @property
    def message_dir(self) -> Path:
        return self.db_storage / "message"


def _normalize(db_dir: str | Path) -> Path:
    path = Path(db_dir).expanduser()
    if path.is_dir() and (path / "db_storage").is_dir():
        return path / "db_storage"
    if path.name == "db_storage" and path.is_dir():
        return path
    if not path.exists():
        raise UnsupportedSchemaError(f"路径不存在: {path}")
    # Last attempt: search one level down for db_storage.
    for child in path.iterdir():
        if child.is_dir() and (child / "db_storage").is_dir():
            return child / "db_storage"
    raise UnsupportedSchemaError(f"没有找到 db_storage: {path}")


def _find_account(db_storage: Path) -> tuple[Path | None, str]:
    current = db_storage
    for _ in range(4):
        current = current.parent
        match = _WXID.match(current.name)
        if match:
            return current, match.group(1)
    return None, ""


def find_layout(db_dir: str | Path) -> DataLayout:
    db_storage = _normalize(db_dir)
    message_dir = db_storage / "message"
    shards = sorted(
        p
        for p in message_dir.glob("message_*.db")
        if p.is_file() and re.fullmatch(r"message_\d+\.db", p.name)
    )
    if not shards:
        raise UnsupportedSchemaError(f"没有找到 message_*.db: {message_dir}")

    session_db = db_storage / "session" / "session.db"
    contact_db = db_storage / "contact" / "contact.db"
    account_dir, account_wxid = _find_account(db_storage)
    attach_dir = account_dir / "msg" / "attach" if account_dir else None

    wal_bytes = 0
    wal_files: list[str] = []
    for shard in shards:
        wal = shard.with_name(shard.name + "-wal")
        if wal.exists() and wal.stat().st_size > 0:
            wal_bytes += wal.stat().st_size
            wal_files.append(wal.name)

    return DataLayout(
        db_storage=db_storage,
        shards=shards,
        session_db=session_db if session_db.exists() else None,
        contact_db=contact_db if contact_db.exists() else None,
        account_dir=account_dir,
        account_wxid=account_wxid,
        attach_dir=attach_dir if attach_dir and attach_dir.exists() else None,
        wal_bytes=wal_bytes,
        wal_files=wal_files,
    )
