"""Fills and submits an application form. Works across Greenhouse, Lever and Ashby, which are
plain HTML forms with labelled fields; per-ATS quirks live in SITE_TWEAKS.
"""
from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path

from playwright.sync_api import Page

from ..profile_parser import Profile
from . import ManualAction, Submitted
from .browser import dump_html, guard, shot
from .fields import CONSENT, NEVER, Field, classify, map_questions, profile_values, read_form

log = logging.getLogger(__name__)

SUBMIT_TEXTS = ["submit application", "submit your application", "submit", "send application", "apply"]
GONE_TEXTS = re.compile(
    r"(404|not found|no longer (accepting|available|open)|position (has been )?(closed|filled)|"
    r"posting (is )?(closed|expired)|this job is no longer)", re.I)
CONFIRM_TEXTS = re.compile(
    r"(thank you|thanks for (applying|your application)|application (was )?(received|submitted|sent)|"
    r"we('| ha)?ve received your application|successfully applied|your application has been)", re.I)

# Per-site entry points: where the form lives when the posting URL isn't the form itself.
SITE_TWEAKS = {
    "lever": lambda url: url if url.rstrip("/").endswith("/apply") else url.rstrip("/") + "/apply",
    "ashby": lambda url: url if "/application" in url else url.rstrip("/") + "/application",
    "greenhouse": lambda url: url,
}


def _write_temp(data: bytes, name: str) -> str:
    path = Path(tempfile.mkdtemp()) / name
    path.write_bytes(data)
    return str(path)


def open_form(page: Page, url: str, ats: str, artifacts: Path) -> None:
    target = SITE_TWEAKS.get(ats, lambda u: u)(url)
    log.info("opening %s", target)
    page.goto(target, wait_until="domcontentloaded")
    page.wait_for_timeout(2500)
    guard(page, artifacts, "open")
    # Some boards hide the form behind an "Apply" / "Apply for this job" button.
    for text in ["apply for this job", "apply now", "apply to this job", "i'm interested"]:
        try:
            btn = page.get_by_role("button", name=re.compile(text, re.I)).first
            if btn.is_visible(timeout=700):
                btn.click()
                page.wait_for_timeout(2000)
                break
        except Exception:
            continue
    guard(page, artifacts, "form")
    head = f"{page.title()} {page.inner_text('body')[:1500] if page.locator('body').count() else ''}"
    if GONE_TEXTS.search(head):
        shot(page, artifacts, "posting-gone")
        raise ManualAction("The posting is closed or no longer accepting applications",
                           {"page_title": page.title()})


PARSING = re.compile(r"(analy[sz]ing|parsing|uploading|processing) (your )?(resume|cv|file)", re.I)


def wait_for_parser(page: Page, timeout_ms: int = 25000) -> None:
    """Lever/Greenhouse parse an uploaded resume and rewrite fields; filling before that is lost."""
    waited = 0
    while waited < timeout_ms:
        body = page.inner_text("body")[:4000] if page.locator("body").count() else ""
        if not PARSING.search(body):
            page.wait_for_timeout(1200)  # let the rewrite settle
            return
        page.wait_for_timeout(1000)
        waited += 1000
    log.warning("resume parser still running after %ss", timeout_ms // 1000)


def fill(page: Page, profile: Profile, app: dict, files: dict[str, bytes], artifacts: Path) -> dict:
    """Fill every field we can justify. Returns a report of what was filled and what was skipped."""
    values = profile_values(profile)
    answers = {a["key"]: a for a in app.get("screening_answers") or []}
    fields = read_form(page)
    if not fields:
        dump_html(page, artifacts, "no-fields")
        raise ManualAction("Could not find a fillable application form on the page")

    report: dict[str, list] = {"filled": [], "skipped": [], "uploaded": [], "unverified": []}

    # Uploads go first: sites parse the resume and rewrite the form, which wipes anything typed before.
    uploaded_any = False
    for f in fields:
        if f.kind != "file" or NEVER.search(f.label):
            continue
        key = classify(f.label)
        doc = "cover_pdf" if key == "cover_letter" else "resume_pdf"
        if key not in ("resume", "cover_letter") and "resume" not in f.name.lower():
            report["skipped"].append({"label": f.label, "why": "unknown file field"})
            continue
        name = "Christopher_Arowolo_Cover_Letter.pdf" if doc == "cover_pdf" else "Christopher_Arowolo_Resume.pdf"
        try:
            f.locator.set_input_files(_write_temp(files[doc], name))
            uploaded_any = True
            report["uploaded"].append({"label": f.label, "file": name})
        except Exception as e:
            report["skipped"].append({"label": f.label, "why": f"upload failed: {type(e).__name__}: {e}"})
    if uploaded_any:
        page.wait_for_timeout(1500)
        wait_for_parser(page)
        fields = read_form(page)  # the parser may have replaced every control
    unknown: list[tuple[int, Field]] = []
    questions: list[str] = []

    for f in fields:
        if NEVER.search(f.label):
            report["skipped"].append({"label": f.label, "why": "demographic/EEOC — never auto-answered"})
            continue
        if f.kind == "file":
            continue
        key = classify(f.label)
        try:
            if key and key in values and values[key] and f.kind in ("text", "textarea"):
                f.locator.fill(values[key])
                report["filled"].append({"label": f.label, "value": values[key][:60], "source": "profile",
                                         "_locator": f.locator, "_full": values[key]})
                continue

            if key == "cover_letter" and f.kind == "textarea":
                f.locator.fill(app["cover_letter_text"])
                report["filled"].append({"label": f.label, "value": "cover letter text", "source": "generated",
                                         "_locator": f.locator, "_full": app["cover_letter_text"]})
                continue

            if f.kind == "checkbox":
                if CONSENT.search(f.label) and f.required:
                    f.locator.check()
                    report["filled"].append({"label": f.label, "value": "checked", "source": "consent (required to apply)"})
                else:
                    report["skipped"].append({"label": f.label, "why": "optional or unrecognised checkbox"})
                continue

            # Anything left is a screening question: only your approved answers may fill it.
            unknown.append((len(questions), f))
            questions.append(f.label)
        except Exception as e:
            report["skipped"].append({"label": f.label, "why": f"{type(e).__name__}: {e}"})

    mapping = map_questions(questions, list(answers.values()))
    for idx, f in unknown:
        key = mapping.get(idx)
        answer = (answers.get(key, {}).get("answer") or "").strip() if key else ""
        if not answer:
            if f.required:
                shot(page, artifacts, "unanswered")
                raise ManualAction(f"Required question I have no approved answer for: “{f.label[:120]}”",
                                   {"question": f.label})
            report["skipped"].append({"label": f.label, "why": "optional, no approved answer"})
            continue
        try:
            if f.kind in ("text", "textarea"):
                f.locator.fill(answer)
            elif f.kind in ("select", "radio"):
                choice = _closest_option(answer, f.options)
                if not choice:
                    if f.required:
                        raise ManualAction(f"Required choice I can't answer safely: “{f.label[:120]}”",
                                           {"question": f.label, "options": f.options})
                    report["skipped"].append({"label": f.label, "why": "no matching option"})
                    continue
                if f.kind == "select":
                    f.locator.select_option(label=choice)
                else:
                    page.get_by_role("radio", name=re.compile(re.escape(choice), re.I)).first.check()
            report["filled"].append({"label": f.label, "value": answer[:60], "source": f"answer:{key}",
                                     "_locator": f.locator if f.kind in ("text", "textarea") else None,
                                     "_full": answer})
        except ManualAction:
            raise
        except Exception as e:
            report["skipped"].append({"label": f.label, "why": f"{type(e).__name__}: {e}"})

    verify(page, report)
    return report


def verify(page: Page, report: dict) -> None:
    """Re-read text fields and refill any the site cleared; anything still empty is reported."""
    for entry in report["filled"]:
        loc = entry.pop("_locator", None)
        if loc is None or entry.get("value") in (None, "checked"):
            continue
        try:
            if loc.input_value().strip():
                continue
            loc.fill(entry["_full"])
            page.wait_for_timeout(200)
            if not loc.input_value().strip():
                report["unverified"].append({"label": entry["label"], "why": "field cleared by the site"})
        except Exception as e:
            report["unverified"].append({"label": entry["label"], "why": f"{type(e).__name__}: {e}"})
    for entry in report["filled"]:
        entry.pop("_full", None)


def _closest_option(answer: str, options: list[str]) -> str | None:
    """Pick an option only when the intent is unambiguous (yes/no or a clear substring)."""
    a = answer.strip().lower()
    for opt in options:
        if opt.strip().lower() == a:
            return opt
    yes = a.startswith("yes") or a == "true"
    no = a.startswith("no") or a == "false"
    for opt in options:
        o = opt.strip().lower()
        if yes and o in ("yes", "y"):
            return opt
        if no and o in ("no", "n"):
            return opt
    matches = [o for o in options if o.strip().lower() in a and len(o.strip()) > 2]
    return matches[0] if len(matches) == 1 else None


def submit_form(page: Page, artifacts: Path, no_submit: bool) -> Submitted:
    guard(page, artifacts, "pre-submit")
    before = shot(page, artifacts, "filled-form")
    if no_submit:
        dump_html(page, artifacts, "filled-form")
        raise ManualAction("Dry run: form filled but not submitted", {"screenshot": before})

    button = None
    for text in SUBMIT_TEXTS:
        try:
            candidate = page.get_by_role("button", name=re.compile(rf"^\s*{re.escape(text)}\s*$", re.I)).last
            if candidate.is_visible(timeout=800) and candidate.is_enabled():
                button = candidate
                break
        except Exception:
            continue
    if button is None:
        dump_html(page, artifacts, "no-submit-button")
        raise ManualAction("Could not find the submit button", {"screenshot": before})

    button.click()
    page.wait_for_timeout(6000)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    after = shot(page, artifacts, "after-submit")
    body = page.inner_text("body")[:6000] if page.locator("body").count() else ""

    if CONFIRM_TEXTS.search(body):
        return Submitted("Submitted — confirmation shown on the page",
                         {"screenshot": after, "url": page.url, "confirmation": CONFIRM_TEXTS.search(body).group(0)})
    # No confirmation: never assume it worked.
    dump_html(page, artifacts, "unconfirmed")
    raise ManualAction("Clicked submit but saw no confirmation — check whether it went through",
                       {"screenshot": after, "url": page.url})
