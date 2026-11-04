"""Safe output file names."""

from __future__ import annotations

import re

_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize(name: str, fallback: str = "chat") -> str:
    text = _BAD.sub("_", (name or "").strip()).strip(" .")
    if not text:
        text = fallback
    if text.upper() in _RESERVED:
        text = "_" + text
    return text[:80]
