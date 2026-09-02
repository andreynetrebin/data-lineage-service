"""Тесты Telegram-алертов."""
from lineage_service.alerts import TelegramAlerter
from lineage_service.model import Node
from lineage_service.snapshot_diff import diff_graphs


def diff_with_changes():
    return diff_graphs([Node(id="a", system="s", type="t", name="A")], [],
                       [Node(id="b", system="s", type="t", name="B")], [])


def test_notify_diff_sends_message():
    sent = {}

    def fake_poster(url, chat_id, text):
        sent.update(url=url, chat_id=chat_id, text=text)
        return True

    alerter = TelegramAlerter("TOKEN123", "chat42", poster=fake_poster)
    assert alerter.notify_diff(diff_with_changes()) is True

    assert "TOKEN123" in sent["url"]
    assert sent["chat_id"] == "chat42"
    assert "+ node b (B)" in sent["text"]
    assert "- node a (A)" in sent["text"]


def test_notify_diff_skips_empty_diff():
    called = []

    def fake_poster(url, chat_id, text):
        called.append(1)
        return True

    alerter = TelegramAlerter("TOKEN123", "chat42", poster=fake_poster)
    assert alerter.notify_diff(diff_graphs([], [], [], [])) is False
    assert called == []
