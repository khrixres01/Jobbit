from __future__ import annotations

import html
import logging
import re
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from ..config import settings

log = logging.getLogger(__name__)


def client() -> httpx.Client:
    http = settings()["http"]
    return httpx.Client(
        timeout=http["timeout_seconds"],
        headers={"User-Agent": http["user_agent"], "Accept": "application/json"},
        follow_redirects=True,
    )


def get_json(http: httpx.Client, url: str, **params):
    """GET JSON; returns None (and logs) on 4xx so an invalid board token is skipped."""
    r = http.get(url, params=params or None)
    if 400 <= r.status_code < 500:
        log.warning("%s -> HTTP %s, skipping", url, r.status_code)
        return None
    r.raise_for_status()
    return r.json()


def html_to_text(raw: str | None) -> str:
    if not raw:
        return ""
    # Greenhouse double-escapes its HTML content
    text = BeautifulSoup(html.unescape(raw), "html.parser").get_text("\n")
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def parse_date(value) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)):
            # Lever uses epoch ms, others epoch seconds
            return datetime.fromtimestamp(value / 1000 if value > 1e12 else value, tz=timezone.utc)
        dt = dateparser.parse(str(value))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, OverflowError):
        return None


def mentions_remote(*texts: str | None) -> bool:
    return any(t and re.search(r"\bremote\b", t, re.I) for t in texts)
