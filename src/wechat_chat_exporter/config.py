"""JSON config file support.

A config file removes the need to repeat long paths on every command::

    wce init
    wce export --config wce.json

Explicit CLI flags always win over config values.  The file never contains
the database key itself, only the path to a key file.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .errors import UsageError

CONFIG_NAME = "wce.json"

# Keys that may appear in a config file.  They match argparse dest names.
CONFIG_KEYS = {
    "db_dir",
    "key_file",
    "key_stdin",
    "out",
    "session",
    "formats",
    "split",
    "limit",
    "since",
    "until",
    "timezone",
    "me",
    "label_me",
    "exclude_system",
    "image_mode",
    "image_key_file",
    "pdf_font",
    "overwrite",
    "strict_wal",
    "strict_hmac",
    "keep_work",
    "work_dir",
    "verbose",
}


def load_config(path: str | Path) -> dict[str, object]:
    file = Path(path)
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except OSError as exc:
        raise UsageError(f"无法读取配置文件: {file}") from exc
    except ValueError as exc:
        raise UsageError(f"配置文件不是合法 JSON: {file}") from exc
    if not isinstance(data, dict):
        raise UsageError("配置文件顶层必须是 JSON 对象")
    unknown = set(data) - CONFIG_KEYS
    if unknown:
        raise UsageError(f"配置文件包含未知字段: {', '.join(sorted(unknown))}")
    return data


def apply_config(args: argparse.Namespace) -> argparse.Namespace:
    """Fill unset argparse values from ``--config`` or ``./wce.json``."""
    path = getattr(args, "config", None)
    if not path and Path(CONFIG_NAME).is_file():
        path = CONFIG_NAME
    if not path:
        return args
    data = load_config(path)
    for key, value in data.items():
        if hasattr(args, key) and getattr(args, key) is None:
            setattr(args, key, value)
    return args


def finalize_args(args: argparse.Namespace) -> argparse.Namespace:
    """Apply defaults after config merging and check required values."""
    defaults = {
        "formats": "csv,html",
        "split": "auto",
        "image_mode": "auto",
        "overwrite": "skip",
        "label_me": "我",
    }
    for key, value in defaults.items():
        if getattr(args, key, None) is None:
            setattr(args, key, value)

    command = getattr(args, "command", "")
    choices = {
        "split": {"auto", "none", "year", "month"},
        "image_mode": {"none", "placeholder", "auto", "inline", "file"},
        "overwrite": {"skip", "force", "ask"},
    }
    for key, allowed in choices.items():
        candidate = getattr(args, key, None)
        if candidate is not None and candidate not in allowed:
            raise UsageError(f"{key} 只能是 {', '.join(sorted(allowed))}：{candidate}")

    if command in ("doctor", "sessions", "export") and not getattr(args, "db_dir", None):
        raise UsageError("请用 --db-dir 或配置文件指定微信 db_storage 目录")
    if command == "export":
        if not getattr(args, "session", None):
            raise UsageError("请用 --session 或配置文件指定要导出的会话")
        if not getattr(args, "out", None):
            raise UsageError("请用 --out 或配置文件指定输出目录")
    if command == "validate" and not getattr(args, "out", None):
        raise UsageError("请用 --out 或配置文件指定要校验的目录")
    return args
