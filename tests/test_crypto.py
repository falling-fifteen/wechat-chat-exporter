from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fixtures.build_sqlcipher import TEST_KEY

from wechat_chat_exporter.crypto.sqlcipher4 import decrypt_file
from wechat_chat_exporter.errors import DecryptError


def test_decrypt_roundtrip(account: Path, tmp_path: Path) -> None:
    src = account / "db_storage" / "message" / "message_0.db"
    dst = tmp_path / "plain.db"
    stats = decrypt_file(src, dst, TEST_KEY)
    assert stats.pages > 0
    assert stats.hmac_ok == stats.pages
    con = sqlite3.connect(dst)
    try:
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        names = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "Name2Id" in names
        assert any(name.startswith("Msg_") for name in names)
    finally:
        con.close()


def test_wrong_key_rejected(account: Path, tmp_path: Path) -> None:
    src = account / "db_storage" / "message" / "message_0.db"
    with pytest.raises(DecryptError):
        decrypt_file(src, tmp_path / "bad.db", b"\x00" * 32)


def test_truncated_file_rejected(account: Path, tmp_path: Path) -> None:
    src = account / "db_storage" / "message" / "message_0.db"
    broken = tmp_path / "broken.db"
    broken.write_bytes(src.read_bytes()[:-100])
    with pytest.raises(DecryptError):
        decrypt_file(broken, tmp_path / "out.db", TEST_KEY)
