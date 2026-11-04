"""How a user supplies the database key and the optional image key.

The tool never extracts keys from a running WeChat process.  A key is read
from a file, an environment variable, stdin, or an interactive prompt, and is
never accepted as a plain-text command-line argument.
"""

from __future__ import annotations

import contextlib
import getpass
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from ..errors import KeySourceError

ENV_KEY = "WECHAT_CHAT_EXPORTER_KEY"
_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")


def validate_key_hex(value: str) -> bytes:
    value = (value or "").strip()
    if not _HEX64.match(value):
        raise KeySourceError("数据库密钥必须是 64 个十六进制字符")
    return bytes.fromhex(value)


def load_key(
    key_file: str | os.PathLike[str] | None = None,
    *,
    key_stdin: bool = False,
    prompt: bool = True,
) -> bytes:
    if key_file:
        path = Path(key_file)
        try:
            return validate_key_hex(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise KeySourceError(f"无法读取密钥文件: {path}") from exc

    env = os.environ.get(ENV_KEY)
    if env:
        return validate_key_hex(env)

    if key_stdin:
        value = sys.stdin.readline()
        if not value:
            raise KeySourceError("stdin 没有提供密钥")
        return validate_key_hex(value)

    if prompt and sys.stdin.isatty():
        value = getpass.getpass("请输入 64 位微信数据库密钥（输入不回显）: ")
        return validate_key_hex(value)

    raise KeySourceError(
        "缺少数据库密钥：请使用 --key-file、环境变量 WECHAT_CHAT_EXPORTER_KEY，"
        "或通过 --key-stdin / 交互输入提供"
    )


@dataclass
class ImageKey:
    xor_key: int = 0
    aes_keys: list[bytes] = field(default_factory=list)
    account: str | None = None


def _decode_aes_key(value: object) -> bytes | None:
    if not isinstance(value, (str, bytes)):
        return None
    if isinstance(value, bytes):
        if len(value) == 16:
            return value
        value = value.decode("ascii", "ignore")
    value = value.strip()
    if re.fullmatch(r"[0-9a-fA-F]{32}", value):
        return bytes.fromhex(value)
    if len(value) == 16:
        return value.encode("ascii", "ignore")
    return None


def _derive_from_code(code: int | str, wxid: str) -> bytes:
    raw = f"{code}{wxid}".encode()
    return hashlib.md5(raw).hexdigest()[:16].encode("ascii")


def load_image_key(
    path: str | os.PathLike[str] | None,
    account_wxid: str | None = None,
) -> ImageKey | None:
    if not path:
        return None
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise KeySourceError(f"无法读取图片密钥文件: {path}") from exc

    keys: list[bytes] = []
    xor_key = 0
    account: str | None = None

    if isinstance(data, dict) and "accounts" in data:
        accounts = data.get("accounts") or []
        chosen = None
        for item in accounts:
            if not isinstance(item, dict):
                continue
            if account_wxid and item.get("wxid") == account_wxid:
                chosen = item
                break
            if chosen is None:
                chosen = item
        if chosen:
            account = chosen.get("wxid")
            for entry in chosen.get("keys") or []:
                if not isinstance(entry, dict) or "code" not in entry:
                    continue
                code = entry["code"]
                if account:
                    keys.append(_derive_from_code(code, account))
                with contextlib.suppress(TypeError, ValueError):
                    xor_key = int(code) & 0xFF
    elif isinstance(data, dict):
        account = data.get("account")
        try:
            xor_key = int(data.get("xor_key", 0)) & 0xFF
        except (TypeError, ValueError):
            xor_key = 0
        for name in ("aes_key_hex", "aes_key", "key"):
            decoded = _decode_aes_key(data.get(name))
            if decoded:
                keys.append(decoded)
    elif isinstance(data, list):
        for item in data:
            decoded = _decode_aes_key(item)
            if decoded:
                keys.append(decoded)

    # De-duplicate while preserving order.
    seen: set[bytes] = set()
    unique: list[bytes] = []
    for key in keys:
        if key not in seen:
            seen.add(key)
            unique.append(key)
    if not unique and xor_key == 0:
        return None
    if account_wxid and account and account != account_wxid:
        raise KeySourceError(f"图片密钥属于账号 {account}，但当前账号是 {account_wxid}")
    return ImageKey(xor_key=xor_key, aes_keys=unique, account=account)
