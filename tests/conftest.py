from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fixtures.build_sqlcipher import TEST_KEY, build_layout  # noqa: E402

from wechat_chat_exporter.db.decrypt import decrypt_layout, make_work_dir  # noqa: E402
from wechat_chat_exporter.db.discovery import find_layout  # noqa: E402


@pytest.fixture(scope="session")
def key() -> bytes:
    return TEST_KEY


@pytest.fixture
def account(tmp_path: Path) -> Path:
    return build_layout(tmp_path, TEST_KEY, messages_per_shard=3)


@pytest.fixture
def key_file(tmp_path: Path) -> Path:
    path = tmp_path / "key.txt"
    path.write_text(TEST_KEY.hex(), encoding="utf-8")
    return path


@pytest.fixture
def decrypted(account: Path):
    layout = find_layout(account / "db_storage")
    work = make_work_dir()
    dec = decrypt_layout(layout, TEST_KEY, work)
    yield dec
    dec.cleanup()
