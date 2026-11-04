from __future__ import annotations

from wechat_chat_exporter.db.contacts import ContactResolver
from wechat_chat_exporter.db.repository import MessageRepository, table_name


def test_count_and_merge(decrypted, account) -> None:
    contacts = ContactResolver(decrypted.session_db, decrypted.contact_db)
    repo = MessageRepository(decrypted, "wxid_test", contacts)
    assert repo.count("wxid_alice0001") == 6

    messages = list(repo.iter_messages("wxid_alice0001"))
    assert len(messages) == 6
    timestamps = [m.timestamp for m in messages]
    assert timestamps == sorted(timestamps)
    assert messages[0].sender_name == "我"
    assert any(m.sender_name == "Alice备注" for m in messages)
    appmsg = [m for m in messages if m.base_type == 49]
    assert appmsg and "一条链接" in appmsg[0].text


def test_limit_returns_latest(decrypted, account) -> None:
    contacts = ContactResolver(decrypted.session_db, decrypted.contact_db)
    repo = MessageRepository(decrypted, "wxid_test", contacts)
    messages = list(repo.iter_messages("wxid_alice0001", limit=2))
    all_messages = list(repo.iter_messages("wxid_alice0001"))
    assert [m.local_id for m in messages] == [m.local_id for m in all_messages[-2:]]


def test_date_filter(decrypted) -> None:
    contacts = ContactResolver(decrypted.session_db, decrypted.contact_db)
    repo = MessageRepository(decrypted, "wxid_test", contacts)
    messages = list(repo.iter_messages("wxid_alice0001", since=1700001000, until=1700002000))
    assert len(messages) == 3


def test_table_name_is_md5() -> None:
    import hashlib

    assert table_name("wxid_alice0001") == "Msg_" + hashlib.md5(b"wxid_alice0001").hexdigest()
