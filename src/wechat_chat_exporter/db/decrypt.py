"""Decrypt a :class:`DataLayout` into a temporary directory."""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from ..crypto.sqlcipher4 import DecryptStats, decrypt_file
from ..errors import DecryptError
from .discovery import DataLayout


@dataclass
class DecryptedLayout:
    work_dir: Path
    shards: list[Path] = field(default_factory=list)
    session_db: Path | None = None
    contact_db: Path | None = None
    stats: list[tuple[str, DecryptStats]] = field(default_factory=list)
    source: DataLayout | None = None

    def cleanup(self) -> None:
        shutil.rmtree(self.work_dir, ignore_errors=True)


def make_work_dir(parent: str | os.PathLike[str] | None = None) -> Path:
    return Path(tempfile.mkdtemp(prefix="wce-", dir=str(parent) if parent else None))


def decrypt_layout(
    layout: DataLayout,
    key: bytes,
    work_dir: Path,
    *,
    strict_hmac: bool = False,
) -> DecryptedLayout:
    work_dir.mkdir(parents=True, exist_ok=True)
    message_out = work_dir / "message"
    message_out.mkdir(exist_ok=True)

    result = DecryptedLayout(work_dir=work_dir, source=layout)
    for shard in layout.shards:
        dst = message_out / shard.name
        stats = decrypt_file(shard, dst, key, strict_hmac=strict_hmac)
        result.shards.append(dst)
        result.stats.append((shard.name, stats))

    if layout.session_db:
        dst = work_dir / "session.db"
        stats = decrypt_file(layout.session_db, dst, key, strict_hmac=strict_hmac)
        result.session_db = dst
        result.stats.append((layout.session_db.name, stats))

    if layout.contact_db:
        dst = work_dir / "contact.db"
        stats = decrypt_file(layout.contact_db, dst, key, strict_hmac=strict_hmac)
        result.contact_db = dst
        result.stats.append((layout.contact_db.name, stats))

    if not result.shards:
        raise DecryptError("没有成功解密任何 message_*.db")
    return result
