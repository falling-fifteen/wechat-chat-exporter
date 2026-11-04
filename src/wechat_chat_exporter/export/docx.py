"""Word (.docx) exporter."""

from __future__ import annotations

import datetime
from io import BytesIO
from pathlib import Path

from ..errors import ExportError
from ..model import local_type as lt
from ..model.message import Message
from .base import ExportContext


def _set_east_asian_font(document) -> None:
    from docx.oxml.ns import qn

    style = document.styles["Normal"]
    style.font.name = "微软雅黑"
    if style.element.rPr is not None and style.element.rPr.rFonts is not None:
        style.element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")


class DocxExporter:
    ext = "docx"

    def write(self, messages: list[Message], path: Path, ctx: ExportContext) -> Path:
        try:
            from docx import Document
            from docx.shared import Cm, RGBColor
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise ExportError(
                "导出 Word 需要安装 python-docx：pip install 'wechat-chat-exporter[docx]'"
            ) from exc

        doc = Document()
        _set_east_asian_font(doc)
        doc.add_heading(ctx.title, level=1)
        doc.add_paragraph(f"共 {len(messages)} 条消息")

        last_day = None
        for msg in messages:
            dt = datetime.datetime.fromtimestamp(msg.timestamp, ctx.tz)
            day = dt.strftime("%Y-%m-%d")
            if day != last_day:
                p = doc.add_paragraph()
                p.add_run(f"—— {day} ——").bold = True
                last_day = day
            p = doc.add_paragraph()
            run = p.add_run(f"{msg.sender_name}  {dt:%H:%M:%S}")
            run.bold = True
            run.font.color.rgb = RGBColor(0x4F, 0x46, 0xE5)
            if msg.base_type == lt.IMAGE and msg.attachment and msg.attachment.data:
                try:
                    doc.add_picture(BytesIO(msg.attachment.data), width=Cm(8))
                    continue
                except Exception:
                    pass
            p.add_run("\n" + (msg.text or ""))

        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        doc.save(str(tmp))
        tmp.replace(path)
        return path
