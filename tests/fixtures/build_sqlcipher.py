"""Build synthetic SQLCipher 4 databases for tests.

No SQLCipher binary is required: a plain SQLite database is created with an
80-byte reserved area (via ``sqlite3_file_control``), then every page is
encrypted using the same layout the exporter decrypts.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import random
import sys
from pathlib import Path

from Crypto.Cipher import AES

PAGE = 4096
RESERVE = 80
SALT = bytes(range(16))
SQLITE_FCNTL_RESERVE_BYTES = 38


def _sqlite_lib() -> ctypes.CDLL:
    candidates = []
    if sys.platform == "win32":
        candidates.append(Path(sys.base_prefix) / "DLLs" / "sqlite3.dll")
        candidates.append(Path(sys.prefix) / "DLLs" / "sqlite3.dll")
    found = ctypes.util.find_library("sqlite3")
    if found:
        candidates.append(Path(found))
    for path in candidates:
        if path and Path(path).exists():
            lib = ctypes.CDLL(str(path))
            lib.sqlite3_open.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_void_p)]
            lib.sqlite3_open.restype = ctypes.c_int
            lib.sqlite3_close.argtypes = [ctypes.c_void_p]
            lib.sqlite3_close.restype = ctypes.c_int
            lib.sqlite3_file_control.argtypes = [
                ctypes.c_void_p,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_void_p,
            ]
            lib.sqlite3_file_control.restype = ctypes.c_int
            lib.sqlite3_exec.argtypes = [
                ctypes.c_void_p,
                ctypes.c_char_p,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_char_p),
            ]
            lib.sqlite3_exec.restype = ctypes.c_int
            return lib
    raise RuntimeError("找不到 sqlite3 动态库，无法生成测试夹具")


def _sql_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def create_plain_db(path: Path, statements: list[str], *, page_size: int = PAGE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    lib = _sqlite_lib()
    db = ctypes.c_void_p()
    if lib.sqlite3_open(str(path).encode("utf-8"), ctypes.byref(db)) != 0:
        raise RuntimeError(f"sqlite3_open failed: {path}")
    try:
        reserve = ctypes.c_int(RESERVE)
        rc = lib.sqlite3_file_control(
            db, b"main", SQLITE_FCNTL_RESERVE_BYTES, ctypes.byref(reserve)
        )
        if rc != 0:
            raise RuntimeError(f"设置 reserve={RESERVE} 失败: {rc}")
        err = ctypes.c_char_p()
        for statement in [f"PRAGMA page_size={page_size}"] + statements:
            rc = lib.sqlite3_exec(db, statement.encode("utf-8"), None, None, ctypes.byref(err))
            if rc != 0:
                message = err.value.decode("utf-8", "replace") if err.value else str(rc)
                raise RuntimeError(f"SQL 失败: {message}\n{statement[:200]}")
    finally:
        lib.sqlite3_close(db)


def encrypt_db(plain: Path, out: Path, key: bytes, *, seed: int = 0) -> None:
    from wechat_chat_exporter.crypto.sqlcipher4 import derive_keys

    data = plain.read_bytes()
    if len(data) % PAGE:
        raise ValueError("plain DB is not page aligned")
    pages = len(data) // PAGE
    enc_key, mac_key = derive_keys(key, SALT)
    rng = random.Random(seed)
    out.parent.mkdir(parents=True, exist_ok=True)

    def hmac_for(block: bytes, pgno: int) -> bytes:
        import hashlib
        import hmac
        import struct

        return hmac.new(mac_key, block + struct.pack("<I", pgno), hashlib.sha512).digest()

    with out.open("wb") as fh:
        for pgno in range(pages):
            page = data[pgno * PAGE : (pgno + 1) * PAGE]
            iv = rng.randbytes(16)
            if pgno == 0:
                cipher = AES.new(enc_key, AES.MODE_CBC, iv=iv).encrypt(page[16 : PAGE - RESERVE])
                block = SALT + cipher + iv
                fh.write(block + hmac_for(block, 0))
            else:
                cipher = AES.new(enc_key, AES.MODE_CBC, iv=iv).encrypt(page[: PAGE - RESERVE])
                block = cipher + iv
                fh.write(block + hmac_for(block, pgno))


def build_layout(root: Path, key: bytes, *, messages_per_shard: int = 3) -> Path:
    """Create a small account with two message shards and one session."""
    account = root / "wxid_test_abcd"
    db_storage = account / "db_storage"
    message_dir = db_storage / "message"
    session_dir = db_storage / "session"
    contact_dir = db_storage / "contact"
    for d in (message_dir, session_dir, contact_dir):
        d.mkdir(parents=True, exist_ok=True)

    alice = "wxid_alice0001"
    me = "wxid_test"
    import hashlib

    table = "Msg_" + hashlib.md5(alice.encode()).hexdigest()

    contact_sql = [
        "CREATE TABLE contact(user_name TEXT, remark TEXT, nick_name TEXT)",
        f"INSERT INTO contact VALUES({_sql_quote(me)}, '我', '我')",
        f"INSERT INTO contact VALUES({_sql_quote(alice)}, 'Alice备注', 'Alice')",
    ]
    session_sql = [
        "CREATE TABLE SessionTable(username TEXT, sort_timestamp INTEGER, summary TEXT)",
        f"INSERT INTO SessionTable VALUES({_sql_quote(alice)}, 1700000000, 'hi')",
    ]

    def message_sql(shard_index: int, sender_row: int, other_row: int) -> list[str]:
        statements = [
            "CREATE TABLE Name2Id(user_name TEXT)",
            "INSERT INTO Name2Id(rowid, user_name) VALUES(100, 'weixin')",
            f"INSERT INTO Name2Id(rowid, user_name) VALUES({sender_row}, {_sql_quote(me)})",
            f"INSERT INTO Name2Id(rowid, user_name) VALUES({other_row}, {_sql_quote(alice)})",
            f"CREATE TABLE {table}("
            "local_id INTEGER PRIMARY KEY AUTOINCREMENT, server_id INTEGER, local_type INTEGER, "
            "sort_seq INTEGER, real_sender_id INTEGER, create_time INTEGER, status INTEGER, "
            "upload_status INTEGER, download_status INTEGER, server_seq INTEGER, "
            "origin_source INTEGER, source TEXT, message_content TEXT, compress_content TEXT, "
            "packed_info_data BLOB, WCDB_CT_message_content INTEGER, WCDB_CT_source INTEGER)",
        ]
        base = 1700000000 + shard_index * 1000
        for i in range(messages_per_shard):
            ts = base + i * 60
            if i % 2 == 0:
                sender = sender_row
                text = f"hello-{shard_index}-{i}"
                lt = 1
            else:
                sender = other_row
                if i == 1:
                    text = (
                        "<msg><appmsg><title>一条链接</title>"
                        "<type>5</type><url>https://example.com</url></appmsg></msg>"
                    )
                    lt = (57 << 32) | 49
                else:
                    text = f"reply-{shard_index}-{i}"
                    lt = 1
            statements.append(
                f"INSERT INTO {table}(server_id, local_type, sort_seq, real_sender_id, "
                f"create_time, message_content) VALUES("
                f"{1000 + shard_index * 100 + i}, {lt}, {ts * 1000}, {sender}, {ts}, "
                f"{_sql_quote(text)})"
            )
        return statements

    plain0 = root / "_plain0.db"
    plain1 = root / "_plain1.db"
    create_plain_db(plain0, message_sql(0, 8, 230))
    create_plain_db(plain1, message_sql(1, 1, 2))
    encrypt_db(plain0, message_dir / "message_0.db", key, seed=1)
    encrypt_db(plain1, message_dir / "message_1.db", key, seed=2)
    plain0.unlink()
    plain1.unlink()

    plain_s = root / "_plain_session.db"
    create_plain_db(plain_s, session_sql)
    encrypt_db(plain_s, session_dir / "session.db", key, seed=3)
    plain_s.unlink()

    plain_c = root / "_plain_contact.db"
    create_plain_db(plain_c, contact_sql)
    encrypt_db(plain_c, contact_dir / "contact.db", key, seed=4)
    plain_c.unlink()

    return account


TEST_KEY = bytes.fromhex("11" * 32)
