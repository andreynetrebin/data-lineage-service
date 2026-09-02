"""Алерты об изменениях графа (Telegram Bot API)."""
from __future__ import annotations

from typing import Callable, Optional

import requests

from .snapshot_diff import DiffResult, summarize


class TelegramAlerter:
    def __init__(self, bot_token: str, chat_id: str,
                 poster: Optional[Callable[[str, str, str], bool]] = None):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._poster = poster or self._post_telegram

    @staticmethod
    def _post_telegram(url: str, chat_id: str, text: str) -> bool:
        try:
            r = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=15)
            return r.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def notify_diff(self, diff: DiffResult, title: str = "Lineage changelog") -> bool:
        lines = summarize(diff)
        if not lines:
            return False
        text = title + "\n" + "\n".join(lines)
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        return self._poster(url, self.chat_id, text)
