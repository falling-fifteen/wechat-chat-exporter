"""Streaming SQLCipher 4 page decryption.

WeChat 4.x stores its databases as SQLCipher 4 pages:

* page size        4096 bytes
* reserved area    80 bytes (16-byte IV + 64-byte HMAC-SHA512)
* page 0           [salt 16][ciphertext 4000][IV 16][HMAC 64]
* other pages      [ciphertext 4016][IV 16][HMAC 64]

The 32-byte database key is used as the PBKDF2 passphrase:
``PBKDF2-HMAC-SHA512(key, salt, 256000, 32)``.

This module deliberately does not know anything about WeChat message tables;
it only turns an encrypted ``message_*.db`` into a plain SQLite database.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import struct
from dataclasses import dataclass
from pathlib import Path

from Crypto.Cipher import AES

from ..errors import DecryptError

PAGE_SIZE = 4096
SALT_SIZE = 16
IV_SIZE = 16
HMAC_SIZE = 64
RESERVE = 80
IV_OFFSET = PAGE_SIZE - RESERVE
KDF_ITERATIONS = 256000
SQLITE_MAGIC = b"SQLite format 3\x00"


@dataclass
class DecryptStats:
    pages: int = 0
    hmac_ok: int = 0
    hmac_failed: int = 0


def derive_keys(key: bytes, salt: bytes) -> tuple[bytes, bytes]:
    if len(key) != 32:
        raise DecryptError("数据库密钥必须是 32 字节")
    enc_key = hashlib.pbkdf2_hmac("sha512", key, salt, KDF_ITERATIONS, dklen=32)
    mac_salt = bytes(b ^ 0x3A for b in salt)
    mac_key = hashlib.pbkdf2_hmac("sha512", enc_key, mac_salt, 2, dklen=32)
    return enc_key, mac_key


def hmac_input(page: bytes, pgno: int) -> bytes:
    """HMAC input: ciphertext + IV + little-endian 1-based page number.

    Page 0 additionally excludes its 16-byte plaintext salt prefix.
    """
    body = page[SALT_SIZE:-HMAC_SIZE] if pgno == 0 else page[:-HMAC_SIZE]
    return body + struct.pack("<I", pgno + 1)


def page_hmac(page: bytes, pgno: int, mac_key: bytes) -> bytes:
    return hmac.new(mac_key, hmac_input(page, pgno), hashlib.sha512).digest()


def _validate_header(dec0: bytes) -> None:
    header = SQLITE_MAGIC + dec0
    page_size = int.from_bytes(header[16:18], "big")
    reserved = header[20]
    write_version = header[18]
    read_version = header[19]
    if page_size != PAGE_SIZE:
        raise DecryptError(f"不支持的页大小: {page_size}（仅支持 4096）")
    if reserved != RESERVE:
        raise DecryptError(f"不支持的 reserve 大小: {reserved}（仅支持 80）")
    if write_version not in (1, 2) or read_version not in (1, 2):
        raise DecryptError("数据库头无效，密钥可能不正确")


def decrypt_file(
    src: str | os.PathLike[str],
    dst: str | os.PathLike[str],
    key: bytes,
    *,
    strict_hmac: bool = False,
) -> DecryptStats:
    """Decrypt one SQLCipher 4 database, page by page.

    The output is written to ``dst`` atomically (``dst.tmp`` then replace).
    """
    src_path = Path(src)
    dst_path = Path(dst)
    size = src_path.stat().st_size
    if size == 0 or size % PAGE_SIZE:
        raise DecryptError(f"文件大小不是 {PAGE_SIZE} 的整数倍: {src_path.name}")
    pages = size // PAGE_SIZE

    with src_path.open("rb") as fh:
        page0 = fh.read(PAGE_SIZE)
        if len(page0) != PAGE_SIZE:
            raise DecryptError(f"无法读取第 0 页: {src_path.name}")
        salt = page0[:SALT_SIZE]
        enc_key, mac_key = derive_keys(key, salt)

        iv0 = page0[IV_OFFSET : IV_OFFSET + IV_SIZE]
        dec0 = AES.new(enc_key, AES.MODE_CBC, iv=iv0).decrypt(page0[SALT_SIZE:IV_OFFSET])
        _validate_header(dec0)

        stats = DecryptStats(pages=pages)
        if hmac.compare_digest(page_hmac(page0, 0, mac_key), page0[-HMAC_SIZE:]):
            stats.hmac_ok += 1
        else:
            stats.hmac_failed += 1
            if strict_hmac:
                raise DecryptError("第 0 页 HMAC 校验失败：密钥错误或文件损坏")

        tmp = dst_path.with_name(dst_path.name + ".tmp")
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with tmp.open("wb") as out:
                out.write(SQLITE_MAGIC + dec0 + b"\x00" * RESERVE)
                for pgno in range(1, pages):
                    page = fh.read(PAGE_SIZE)
                    if len(page) != PAGE_SIZE:
                        raise DecryptError(f"第 {pgno} 页不完整: {src_path.name}")
                    iv = page[IV_OFFSET : IV_OFFSET + IV_SIZE]
                    dec = AES.new(enc_key, AES.MODE_CBC, iv=iv).decrypt(page[:IV_OFFSET])
                    out.write(dec + b"\x00" * RESERVE)
                    if hmac.compare_digest(page_hmac(page, pgno, mac_key), page[-HMAC_SIZE:]):
                        stats.hmac_ok += 1
                    else:
                        stats.hmac_failed += 1
            os.replace(tmp, dst_path)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
    return stats
