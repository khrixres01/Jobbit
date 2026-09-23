"""Browser setup, evidence capture, and the checks that stop a submission."""
from __future__ import annotations

import logging
import re
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from . import ManualAction

log = logging.getLogger(__name__)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/131.0.0.0 Safari/537.36")

CAPTCHA_MARKERS = [
    "iframe[src*='recaptcha']", "iframe[src*='hcaptcha']", "iframe[src*='challenges.cloudflare.com']",
    "div.g-recaptcha", "div.h-captcha", "div.cf-turnstile", "#px-captcha",
    # note: .grecaptcha-badge is deliberately absent — it is the silent/invisible variant
]
LOGIN_MARKERS = re.compile(r"\b(sign in to (apply|continue)|log in to (apply|continue)|create an account to apply)\b", re.I)


@contextmanager
def browser_page(artifacts: Path, headless: bool = True):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(user_agent=UA, viewport={"width": 1366, "height": 900},
                                      locale="en-US", accept_downloads=False)
        context.set_default_timeout(20000)
        page = context.new_page()
        page.on("dialog", lambda d: d.dismiss())
        try:
            yield page
        finally:
            browser.close()


def shot(page: Page, artifacts: Path, name: str) -> str:
    path = artifacts / f"{name}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
    except Exception:
        log.warning("could not screenshot %s", name)
    return str(path)


def dump_html(page: Page, artifacts: Path, name: str) -> None:
    try:
        (artifacts / f"{name}.html").write_text(page.content(), encoding="utf-8")
    except Exception:
        pass


def _is_silent_badge(el) -> bool:
    """The invisible-reCAPTCHA badge sits in a .grecaptcha-badge container and needs no human."""
    try:
        return bool(el.evaluate("e => !!e.closest('.grecaptcha-badge')"))
    except Exception:
        return False


def guard(page: Page, artifacts: Path, stage: str) -> None:
    """Stop before anything that could submit a form we don't fully understand.

    Only an *interactive* challenge blocks. Greenhouse and friends put Google's invisible
    reCAPTCHA badge on every form; it scores silently, so treating it as a blocker would hand
    back nearly every application. CAPTCHAs are never solved or bypassed.
    """
    for selector in CAPTCHA_MARKERS:
        try:
            el = page.locator(selector).first
            if not el.is_visible(timeout=800) or _is_silent_badge(el):
                continue
            box = el.bounding_box()
            if not box or box["width"] < 120 or box["height"] < 40:
                continue
            shot(page, artifacts, f"captcha-{stage}")
            raise ManualAction("CAPTCHA challenge on the application form — finish this one by hand",
                               {"stage": stage, "selector": selector, "size": box})
        except ManualAction:
            raise
        except Exception:
            continue
    body = (page.inner_text("body")[:4000] if page.locator("body").count() else "")
    if LOGIN_MARKERS.search(body):
        shot(page, artifacts, f"login-{stage}")
        raise ManualAction("The site wants an account/login before applying", {"stage": stage})
