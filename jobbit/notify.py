from __future__ import annotations

import logging

import httpx

from .config import secrets

log = logging.getLogger(__name__)


def telegram(text: str) -> bool:
    s = secrets()
    if not (s.telegram_token and s.telegram_chat_id):
        log.info("Telegram not configured; would send: %s", text)
        return False
    r = httpx.post(
        f"https://api.telegram.org/bot{s.telegram_token}/sendMessage",
        json={"chat_id": s.telegram_chat_id, "text": text, "disable_web_page_preview": True},
        timeout=20,
    )
    if r.status_code != 200:
        log.error("Telegram send failed: %s %s", r.status_code, r.text[:200])
        return False
    return True
