"""WeChat ``.dat`` image containers.

The container format is detected by magic bytes, not by a guessed version:

* already-valid JPEG / PNG / GIF / WebP / BMP -> use as-is
* ``07 08 56 31 08 07`` -> legacy container, XOR fallback
* ``07 08 56 32 08 07`` -> AES-ECB + XOR container
* ``WXGF`` wrapper -> scan for an embedded JPEG/PNG

Only a user-supplied image key is used; this module never reads WeChat memory.
"""

from __future__ import annotations

import contextlib
import struct

from Crypto.Cipher import AES

MAGIC_V1 = bytes([0x07, 0x08, 0x56, 0x31, 0x08, 0x07])
MAGIC_V2 = bytes([0x07, 0x08, 0x56, 0x32, 0x08, 0x07])


def detect_ext(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:4] == b"\x89PNG":
        return "png"
    if data[:3] == b"GIF":
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:2] == b"BM":
        return "bmp"
    return ""


def _xor(data: bytes, key: int) -> bytes:
    return bytes(b ^ key for b in data)


def _remove_pkcs7(data: bytes) -> bytes:
    if not data:
        raise ValueError("empty data")
    pad = data[-1]
    if pad <= 0 or pad > 16 or pad > len(data):
        raise ValueError("invalid padding")
    return data[:-pad]


def _decrypt_v4(data: bytes, key: bytes, xor_key: int) -> bytes:
    if len(data) < 15:
        raise ValueError("container too small")
    body = data[15:]
    aes_size = struct.unpack_from("<I", data, 6)[0]
    xor_size = struct.unpack_from("<I", data, 10)[0]
    padded = aes_size + (16 - (aes_size % 16 or 16))
    if padded > len(body):
        raise ValueError("invalid aes_size")
    aes_block = body[:padded]
    aes_plain = b""
    if aes_block:
        aes_plain = _remove_pkcs7(AES.new(key, AES.MODE_ECB).decrypt(aes_block))
    rest = body[padded:]
    if xor_size > 0:
        cut = max(0, len(rest) - xor_size)
        raw, tail = rest[:cut], _xor(rest[cut:], xor_key)
    else:
        raw, tail = rest, b""
    return aes_plain + raw + tail


def _unwrap_wxgf(data: bytes) -> bytes:
    if data[:4] != b"WXGF":
        return data
    for offset in range(4, min(len(data), 8192)):
        if detect_ext(data[offset:]):
            return data[offset:]
    return data


def key_candidates(aeskey: str) -> list[bytes]:
    """Turn an XML ``aeskey`` attribute into candidate 16-byte AES keys."""
    aeskey = (aeskey or "").strip()
    out: list[bytes] = []
    if len(aeskey) == 32:
        with contextlib.suppress(ValueError):
            out.append(bytes.fromhex(aeskey))
        out.append(aeskey.encode("ascii", "ignore")[:16].ljust(16, b"\x00"))
    elif len(aeskey) == 16:
        out.append(aeskey.encode("ascii", "ignore"))
    seen: set[bytes] = set()
    unique: list[bytes] = []
    for key in out:
        if key not in seen:
            seen.add(key)
            unique.append(key)
    return unique


def decrypt_dat(
    data: bytes,
    *,
    xor_key: int = 0,
    aes_candidates: list[bytes] | None = None,
) -> tuple[str, bytes]:
    """Return ``(extension, image_bytes)`` or raise ``ValueError``."""
    ext = detect_ext(data)
    if ext:
        return ext, data

    candidates = aes_candidates or []
    version = 2 if data[:6] == MAGIC_V2 else 1 if data[:6] == MAGIC_V1 else 0

    attempts: list[bytes] = []
    if version == 2:
        for key in candidates:
            if len(key) != 16:
                continue
            try:
                attempts.append(_decrypt_v4(data, key, xor_key))
            except (ValueError, KeyError):
                continue
    if version != 2 or not attempts:
        attempts.append(_xor(data, xor_key))

    for attempt in attempts:
        attempt = _unwrap_wxgf(attempt)
        ext = detect_ext(attempt)
        if ext:
            return ext, attempt
    raise ValueError("unsupported image container")
