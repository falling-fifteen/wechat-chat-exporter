"""Shared exporter protocol and context."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from ..model.message import Message


@dataclass
class ExportContext:
    out_dir: Path
    title: str = "聊天记录"
    me_label: str = "我"
    session_username: str = ""
    session_display: str = ""
    bucket: str = ""
    image_mode: str = "auto"
    overwrite: str = "skip"
    tz: datetime.tzinfo | None = None
    warnings: list[str] = field(default_factory=list)


class Exporter(Protocol):
    ext: str

    def write(self, messages: list[Message], path: Path, ctx: ExportContext) -> Path: ...
