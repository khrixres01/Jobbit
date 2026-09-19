"""Loads YAML settings and environment secrets."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
PROFILE_PATH = ROOT / "profile" / "master_profile.md"

# override=True: this project's .env must win over machine-wide vars left by other projects
load_dotenv(ROOT / ".env", override=True)


@lru_cache
def settings() -> dict:
    return yaml.safe_load((ROOT / "config" / "settings.yaml").read_text(encoding="utf-8"))


@lru_cache
def companies() -> dict:
    return yaml.safe_load((ROOT / "config" / "companies.yaml").read_text(encoding="utf-8"))


@dataclass(frozen=True)
class Secrets:
    supabase_url: str | None
    supabase_key: str | None
    anthropic_key: str | None
    gemini_key: str | None
    telegram_token: str | None
    telegram_chat_id: str | None
    dashboard_url: str


def secrets() -> Secrets:
    env = lambda k: os.environ.get(k) or None  # noqa: E731 - treat empty strings as unset
    return Secrets(
        supabase_url=env("SUPABASE_URL"),
        supabase_key=env("SUPABASE_SERVICE_ROLE_KEY"),
        anthropic_key=env("ANTHROPIC_API_KEY"),
        gemini_key=env("GEMINI_API_KEY") or env("GOOGLE_API_KEY"),
        telegram_token=env("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=env("TELEGRAM_CHAT_ID"),
        dashboard_url=env("DASHBOARD_URL") or "http://localhost:3000",
    )
