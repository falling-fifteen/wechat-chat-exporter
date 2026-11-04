"""Render WeChat ``appmsg`` XML into readable text."""

from __future__ import annotations

from ..model.local_type import APPMSG_TYPES
from .xml import find_text, safe_xml


def render_appmsg(text: str, sub_type: int = 0) -> tuple[str, str]:
    """Return ``(display_text, kind_label)`` for an app message."""
    root = safe_xml(text)
    appmsg = root.find("appmsg") if root is not None else None
    if appmsg is None:
        fallback = (text or "").strip()
        return fallback or "[卡片]", APPMSG_TYPES.get(sub_type, "卡片/引用")

    raw_type = find_text(appmsg, "type") or str(sub_type)
    try:
        app_type = int(raw_type)
    except ValueError:
        app_type = sub_type
    kind = APPMSG_TYPES.get(app_type) or APPMSG_TYPES.get(sub_type) or "卡片/引用"

    title = find_text(appmsg, "title")
    des = find_text(appmsg, "des")
    url = find_text(appmsg, "url")
    filename = find_text(appmsg, "appattach/filename") or find_text(appmsg, "filename")
    filesize = find_text(appmsg, "appattach/totallen")

    if app_type == 57:  # quoted / referenced message
        refer = appmsg.find("refermsg")
        refer_title = find_text(refer, "title")
        refer_content = find_text(refer, "content")
        quoted = refer_content or refer_title
        lines = []
        if quoted:
            lines.append("[引用] " + quoted.replace("\n", " ")[:200])
        if title:
            lines.append(title)
        return "\n".join(lines) or "[引用]", kind

    if app_type in (6, 74) or filename:
        size = ""
        if filesize.isdigit():
            size = f" ({_human_size(int(filesize))})"
        return f"[文件] {filename or title}{size}\n{url}".strip(), kind

    if app_type in (2000, 2001):
        return f"[{kind}] {des or title}".strip(), kind

    if title or des:
        body = title or des
        if url and url not in body:
            body = f"{body}\n{url}"
        return body.strip(), kind

    return f"[{kind}]", kind


def _human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f}{unit}" if unit == "B" else f"{value:.1f}{unit}"
        value /= 1024
    return f"{value:.0f}B"
