"""Self-contained HTML chat viewer."""

from __future__ import annotations

import base64
import datetime
import html
from pathlib import Path

from ..model.message import Message
from .base import ExportContext

_CSS = """
body{margin:0;background:#f2f3f5;font-family:"Microsoft YaHei","PingFang SC",sans-serif}
.wrap{max-width:900px;margin:0 auto;padding:24px 16px}
h1{font-size:20px;text-align:center;color:#333;margin:16px 0 4px}
.meta{text-align:center;color:#888;font-size:12px;margin-bottom:24px}
.day{text-align:center;margin:22px 0 10px}
.day span{background:#dcdfe5;color:#666;font-size:12px;padding:3px 10px;border-radius:10px}
.msg{display:flex;margin:10px 0;align-items:flex-start}
.msg.me{flex-direction:row-reverse}
.avatar{width:34px;height:34px;border-radius:4px;flex:0 0 34px;margin:0 8px;background:#c9d6ff;
color:#3949ab;font-size:12px;display:flex;align-items:center;justify-content:center}
.bubble-wrap{max-width:64%}
.name{font-size:11px;color:#999;margin-bottom:3px}
.msg.me .name{text-align:right}
.bubble{background:#fff;padding:9px 12px;border-radius:8px;font-size:14px;line-height:1.55;
color:#222;white-space:pre-wrap;word-break:break-word;box-shadow:0 1px 2px rgba(0,0,0,.05)}
.msg.me .bubble{background:#95ec69}
.time{font-size:10px;color:#b0b0b0;margin-top:3px}
.msg.me .time{text-align:right}
.bubble img{max-width:100%;border-radius:4px;display:block}
.placeholder{color:#999}
"""


def _render_media(msg: Message, ctx: ExportContext, path: Path) -> str:
    att = msg.attachment
    if att and att.data and ctx.image_mode in ("auto", "inline", "file"):
        if ctx.image_mode == "file":
            name = str(msg.extra.get("image_md5") or msg.local_id) + "." + (att.ext or "png")
            img_dir = path.parent / "images"
            img_dir.mkdir(parents=True, exist_ok=True)
            (img_dir / name).write_bytes(att.data)
            return f'<img src="images/{name}" alt="图片">'
        mime = "image/jpeg" if att.ext in ("jpg", "jpeg") else f"image/{att.ext or 'png'}"
        encoded = base64.b64encode(att.data).decode("ascii")
        return f'<img src="data:{mime};base64,{encoded}" alt="图片">'
    return '<span class="placeholder">[图片]</span>'


class HtmlExporter:
    ext = "html"

    def write(self, messages: list[Message], path: Path, ctx: ExportContext) -> Path:
        esc = html.escape
        parts = [
            '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">',
            f"<title>{esc(ctx.title)}</title><style>{_CSS}</style></head>",
            '<body><div class="wrap">',
            f"<h1>{esc(ctx.title)}</h1>",
            (
                f'<div class="meta">共 {len(messages)} 条消息 · 导出时间 '
                f"{datetime.datetime.now():%Y-%m-%d %H:%M}</div>"
            ),
        ]
        last_day = None
        for msg in messages:
            dt = datetime.datetime.fromtimestamp(msg.timestamp, ctx.tz)
            day = dt.strftime("%Y-%m-%d")
            if day != last_day:
                parts.append(f'<div class="day"><span>{day}</span></div>')
                last_day = day
            is_me = msg.sender_name == ctx.me_label
            initial = "我" if is_me else (esc(msg.sender_name)[:1] or "他")
            body = esc(msg.text).replace("\n", "<br>")
            if msg.base_type == 3:
                body = _render_media(msg, ctx, path)
            parts.append(
                f'<div class="msg{" me" if is_me else ""}">'
                f'<div class="avatar">{initial}</div><div class="bubble-wrap">'
                f'<div class="name">{esc(msg.sender_name)}</div>'
                f'<div class="bubble">{body}</div>'
                f'<div class="time">{dt:%H:%M}</div></div></div>'
            )
        parts.append("</div></body></html>")
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text("\n".join(parts), encoding="utf-8")
        tmp.replace(path)
        return path
