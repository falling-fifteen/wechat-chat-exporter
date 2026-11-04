"""Turn raw ``message_content`` into display text plus media hints."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..model import local_type as lt
from .appmsg import render_appmsg
from .xml import regex_attr
from .zstd import to_text


@dataclass
class ParsedContent:
    text: str
    kind: str
    image_md5: str = ""
    image_aeskey: str = ""


def _packed_md5(packed: object) -> str:
    if packed is None:
        return ""
    if isinstance(packed, str):
        try:
            raw = bytes.fromhex(packed)
        except ValueError:
            raw = packed.encode("utf-8", "replace")
    elif isinstance(packed, (bytes, bytearray, memoryview)):
        raw = bytes(packed)
    else:
        return ""
    printable = "".join(chr(b) if 32 <= b <= 126 else " " for b in raw)
    match = re.search(r"\b([0-9a-fA-F]{32})\b", printable)
    return match.group(1).lower() if match else ""


def image_info(content: str, packed: object = None) -> tuple[str, str]:
    """Extract ``(md5, aeskey)`` from an image message."""
    md5 = regex_attr(content, "img", "md5").lower()
    aeskey = regex_attr(content, "img", "aeskey").lower()
    if not md5:
        md5 = _packed_md5(packed)
    return md5, aeskey


def parse_message_content(
    local_type: int,
    message_content: object,
    compress_content: object = None,
    packed_info_data: object = None,
) -> ParsedContent:
    base, sub = lt.split_type(local_type)
    text = to_text(message_content)
    if not text and compress_content is not None:
        text = to_text(compress_content)

    if base == lt.TEXT:
        return ParsedContent(text=text, kind="文字")
    if base == lt.SYSTEM:
        return ParsedContent(text=text or "[系统消息]", kind="系统")
    if base == lt.APPMSG:
        body, kind = render_appmsg(text, sub)
        return ParsedContent(text=body, kind=kind)
    if base == lt.IMAGE:
        md5, aeskey = image_info(text, packed_info_data)
        return ParsedContent(text="[图片]", kind="图片", image_md5=md5, image_aeskey=aeskey)

    placeholder = lt.PLACEHOLDERS.get(base, f"[类型{base}]")
    return ParsedContent(text=placeholder, kind=lt.kind_for(local_type))
