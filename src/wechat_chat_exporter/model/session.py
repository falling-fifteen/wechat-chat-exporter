"""A conversation entry."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Session:
    username: str
    display_name: str = ""
    last_timestamp: int = 0
    summary: str = ""
    message_count: int = 0

    @property
    def is_group(self) -> bool:
        return self.username.endswith("@chatroom")

    @property
    def label(self) -> str:
        return self.display_name or self.username
