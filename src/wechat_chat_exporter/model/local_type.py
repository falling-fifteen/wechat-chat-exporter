"""WeChat 4.x ``local_type`` decoding.

The low 32 bits hold the message type.  The high 32 bits hold a sub-type used
by app messages (quotes, links, files, ...).  Dropping the high bits loses
information, so both values are kept.
"""

from __future__ import annotations

TEXT = 1
IMAGE = 3
VOICE = 34
VIDEO = 43
STICKER = 47
APPMSG = 49
CALL = 50
SYSTEM = 10000

KIND_NAMES = {
    TEXT: "文字",
    IMAGE: "图片",
    VOICE: "语音",
    VIDEO: "视频",
    STICKER: "表情",
    APPMSG: "卡片/引用",
    CALL: "通话",
    SYSTEM: "系统",
}

PLACEHOLDERS = {
    IMAGE: "[图片]",
    VOICE: "[语音]",
    VIDEO: "[视频]",
    STICKER: "[表情]",
    CALL: "[通话]",
}

APPMSG_TYPES = {
    3: "音乐",
    5: "链接",
    6: "文件",
    19: "合并转发",
    33: "小程序",
    36: "小程序",
    51: "视频号",
    57: "引用",
    74: "文件",
    87: "群公告",
    2000: "转账",
    2001: "红包",
}


def split_type(local_type: int) -> tuple[int, int]:
    local_type = int(local_type or 0)
    return local_type & 0xFFFFFFFF, (local_type >> 32) & 0xFFFFFFFF


def base_type(local_type: int) -> int:
    return split_type(local_type)[0]


def kind_for(local_type: int) -> str:
    base, sub = split_type(local_type)
    if base == APPMSG:
        return APPMSG_TYPES.get(sub, "卡片/引用")
    return KIND_NAMES.get(base, f"类型{base}")
