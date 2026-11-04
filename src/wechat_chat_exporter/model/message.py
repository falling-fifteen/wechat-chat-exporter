"""A single normalized message."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, tzinfo
from typing import Any


@dataclass
class Attachment:
    kind: str  # "image" | "voice" | "video" | "file" | ...
    data: bytes | None = None
    ext: str = ""
    source_path: str = ""
    error: str = ""


@dataclass
class Message:
    local_id: int
    server_id: int
    timestamp: int
    sort_seq: int
    sender_id: int
    sender_name: str
    local_type: int
    base_type: int
    sub_type: int
    kind: str
    text: str
    attachment: Attachment | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def time_str(self, tz: tzinfo | None = None) -> str:
        if not self.timestamp:
            return ""
        return datetime.fromtimestamp(self.timestamp, tz=tz).strftime("%Y-%m-%d %H:%M:%S")
