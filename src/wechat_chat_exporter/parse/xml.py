"""Defensive XML helpers for WeChat app messages."""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET

_DOCTYPE = re.compile(r"<!\s*(DOCTYPE|ENTITY)", re.I)
_CDATA = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.S)


def safe_xml(text: str) -> ET.Element | None:
    if not text:
        return None
    if _DOCTYPE.search(text):
        return None
    cleaned = _CDATA.sub(lambda m: html.escape(m.group(1)), text)
    try:
        return ET.fromstring(cleaned)
    except ET.ParseError:
        return None


def find_text(root: ET.Element | None, path: str) -> str:
    if root is None:
        return ""
    node = root.find(path)
    if node is None or node.text is None:
        return ""
    return html.unescape(node.text).strip()


def regex_tag(text: str, tag: str) -> str:
    match = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", text or "", re.S)
    if not match:
        return ""
    return html.unescape(_CDATA.sub(lambda m: m.group(1), match.group(1))).strip()


def regex_attr(text: str, tag: str, attr: str) -> str:
    match = re.search(rf"<{tag}\b[^>]*\b{attr}\s*=\s*[\"']([^\"']+)[\"']", text or "", re.I)
    return match.group(1).strip() if match else ""
