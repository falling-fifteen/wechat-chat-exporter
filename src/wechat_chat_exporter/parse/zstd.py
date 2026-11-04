"""Zstandard helpers.

WeChat stores some long messages compressed with zstd.  Depending on the code
path the value arrives as ``bytes`` or as a hex string, so both are handled.
"""

from __future__ import annotations

import re

import zstandard

ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
_HEX = re.compile(r"^[0-9a-fA-F]+$")
MAX_OUTPUT = 64 * 1024 * 1024


def decode_raw(value: object) -> bytes:
    if isinstance(value, memoryview):
        return bytes(value)
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, str):
        text = value.strip()
        if len(text) >= 8 and len(text) % 2 == 0 and _HEX.fullmatch(text):
            try:
                raw = bytes.fromhex(text)
            except ValueError:
                return text.encode("utf-8", "replace")
            if raw[:4] == ZSTD_MAGIC:
                return raw
        return value.encode("utf-8", "replace")
    return b""


def to_text(value: object) -> str:
    if value is None:
        return ""
    raw = decode_raw(value)
    if raw[:4] == ZSTD_MAGIC:
        raw = decompress(raw)
    return raw.decode("utf-8", "replace").replace("\x00", "").strip()


def decompress(raw: bytes, max_output: int = MAX_OUTPUT) -> bytes:
    """Decompress one or more zstd frames; return the input on failure."""
    try:
        return zstandard.ZstdDecompressor().decompress(raw, max_output_size=max_output)
    except zstandard.ZstdError:
        pass
    try:
        chunks: list[bytes] = []
        dctx = zstandard.ZstdDecompressor()
        reader = dctx.stream_reader(raw)
        while True:
            chunk = reader.read(1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
            if sum(len(c) for c in chunks) > max_output:
                break
        if chunks:
            return b"".join(chunks)
    except zstandard.ZstdError:
        pass
    return raw
