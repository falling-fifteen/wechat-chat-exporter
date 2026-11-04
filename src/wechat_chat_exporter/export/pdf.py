"""PDF exporter (fpdf2)."""

from __future__ import annotations

import datetime
from io import BytesIO
from pathlib import Path

from ..errors import ExportError
from ..model import local_type as lt
from ..model.message import Message
from .base import ExportContext

_FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/PingFang.ttc",
]


def _find_font() -> str:
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    raise ExportError("找不到可用的中文字体，请用 --pdf-font 指定 TTF/TTC 字体文件")


class PdfExporter:
    ext = "pdf"

    def __init__(self, font_path: str | None = None):
        self.font_path = font_path

    def write(self, messages: list[Message], path: Path, ctx: ExportContext) -> Path:
        try:
            from fpdf import FPDF
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise ExportError(
                "导出 PDF 需要安装 fpdf2：pip install 'wechat-chat-exporter[pdf]'"
            ) from exc

        font = self.font_path or _find_font()
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        pdf.add_font("CJK", "", font)
        width = pdf.w - 2 * pdf.l_margin

        pdf.set_font("CJK", "", 13)
        pdf.multi_cell(width, 8, f"{ctx.title}  ·  {len(messages)} 条")
        pdf.ln(2)
        pdf.set_draw_color(200, 205, 212)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + width, pdf.get_y())
        pdf.ln(3)

        last_day = None
        for msg in messages:
            dt = datetime.datetime.fromtimestamp(msg.timestamp, ctx.tz)
            day = dt.strftime("%Y-%m-%d")
            if day != last_day:
                pdf.ln(2)
                pdf.set_font("CJK", "", 8)
                pdf.set_text_color(120, 125, 135)
                pdf.cell(width, 5, day, align="C")
                pdf.ln(5)
                last_day = day

            pdf.set_font("CJK", "", 8)
            pdf.set_text_color(120, 125, 135)
            pdf.multi_cell(width, 4, f"{msg.sender_name}  {dt:%Y-%m-%d %H:%M:%S}")
            pdf.set_text_color(0, 0, 0)

            if msg.base_type == lt.IMAGE and msg.attachment and msg.attachment.data:
                try:
                    pdf.image(BytesIO(msg.attachment.data), w=min(110, width * 0.55))
                except Exception:
                    pdf.set_font("CJK", "", 9)
                    pdf.multi_cell(width, 5, "[图片]")
            else:
                pdf.set_font("CJK", "", 9.5)
                pdf.multi_cell(width, 5.2, msg.text or "")
            pdf.ln(2)

        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        pdf.output(str(tmp))
        tmp.replace(path)
        return path
