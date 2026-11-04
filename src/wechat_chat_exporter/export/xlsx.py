"""Streaming XLSX exporter."""

from __future__ import annotations

from pathlib import Path

from ..errors import ExportError
from ..model.message import Message
from .base import ExportContext


class XlsxExporter:
    ext = "xlsx"

    def write(self, messages: list[Message], path: Path, ctx: ExportContext) -> Path:
        try:
            from openpyxl import Workbook
            from openpyxl.cell import WriteOnlyCell
            from openpyxl.styles import Alignment, Font, PatternFill
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise ExportError(
                "导出 Excel 需要安装 openpyxl：pip install 'wechat-chat-exporter[excel]'"
            ) from exc

        wb = Workbook(write_only=True)
        ws = wb.create_sheet("聊天记录")
        ws.column_dimensions["A"].width = 20
        ws.column_dimensions["B"].width = 12
        ws.column_dimensions["C"].width = 12
        ws.column_dimensions["D"].width = 90

        header = []
        for value in ("时间", "发送者", "类型", "内容"):
            cell = WriteOnlyCell(ws, value=value)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", start_color="4F46E5")
            header.append(cell)
        ws.append(header)

        for msg in messages:
            content = WriteOnlyCell(ws, value=msg.text)
            content.alignment = Alignment(wrap_text=True, vertical="top")
            ws.append([msg.time_str(ctx.tz), msg.sender_name, msg.kind, content])

        tmp = path.with_suffix(path.suffix + ".tmp")
        wb.save(tmp)
        tmp.replace(path)
        return path
