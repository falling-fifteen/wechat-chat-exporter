"""CSV exporter with formula-injection protection."""

from __future__ import annotations

import csv
from pathlib import Path

from ..model.message import Message
from .base import ExportContext

_DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(text: str) -> str:
    stripped = text.lstrip()
    if stripped.startswith(_DANGEROUS):
        return "'" + text
    return text


class CsvExporter:
    ext = "csv"

    def write(self, messages: list[Message], path: Path, ctx: ExportContext) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.writer(fh)
            writer.writerow(["时间", "发送者", "类型", "内容"])
            for msg in messages:
                writer.writerow(
                    [
                        msg.time_str(ctx.tz),
                        msg.sender_name,
                        msg.kind,
                        safe_cell(msg.text),
                    ]
                )
        tmp.replace(path)
        return path
