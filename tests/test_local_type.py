from __future__ import annotations

from wechat_chat_exporter.model.local_type import kind_for, split_type


def test_split_type_keeps_high_bits() -> None:
    assert split_type(244813135921) == (49, 57)
    assert split_type(1) == (1, 0)


def test_kind_for_quote() -> None:
    assert kind_for(244813135921) == "引用"
    assert kind_for(3) == "图片"
    assert kind_for(0xDEAD) == "类型57005"
