"""wechat-chat-exporter — export your own WeChat 4.x chat history."""

from __future__ import annotations

try:  # pragma: no cover - trivial
    from importlib.metadata import version

    __version__ = version("wechat-chat-exporter")
except Exception:  # pragma: no cover - editable/source tree
    __version__ = "0.1.0"

__all__ = ["__version__"]
