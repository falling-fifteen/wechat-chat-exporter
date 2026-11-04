"""One JSON object per line, for downstream processing."""

from __future__ import annotations

import json
from pathlib import Path

from ..model.message import Message
from .base import ExportContext


class JsonlExporter:
    ext = "jsonl"

    def write(self, messages: list[Message], path: Path, ctx: ExportContext) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for msg in messages:
                fh.write(
                    json.dumps(
                        {
                            "time": msg.time_str(ctx.tz),
                            "timestamp": msg.timestamp,
                            "sender": msg.sender_name,
                            "kind": msg.kind,
                            "text": msg.text,
                            "local_id": msg.local_id,
                            "server_id": msg.server_id,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        tmp.replace(path)
        return path
