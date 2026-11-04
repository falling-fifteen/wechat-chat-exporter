"""Logging helpers with mandatory secret redaction."""

from __future__ import annotations

import logging
import re

_KEY_RE = re.compile(r"\b[0-9a-fA-F]{64}\b")


def redact(text: str) -> str:
    """Replace anything that looks like a 64-char database key."""
    return _KEY_RE.sub("<redacted-key>", text)


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        return redact(super().format(record))


def setup_logging(verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger("wechat_chat_exporter")
    if logger.handlers:
        return logger
    handler = logging.StreamHandler()
    handler.setFormatter(RedactingFormatter("%(levelname)s: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.propagate = False
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger("wechat_chat_exporter")
