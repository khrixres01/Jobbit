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
from .fields import (ACCESSIBILITY, CONSENT, NEVER, Field, classify, current_value, find_combobox,
                     find_field, map_questions, pick_option, profile_values, read_form)

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

    accessibility_answer = (answers.get("accommodations", {}).get("answer") or "").strip()
    for f in fields:
        if NEVER.search(f.label):
            # one exception: an accessibility question, answered only from what you stated yourself
            if ACCESSIBILITY.search(f.label) and accessibility_answer:
                choice = _answer_choice(page, f, accessibility_answer)
                if choice:
                    report["filled"].append({"label": f.label, "value": choice, "source": "answer:accommodations"})
                    continue
            report["skipped"].append({"label": f.label, "why": "demographic/EEOC — never auto-answered"})
            continue
        if f.kind == "file":
            continue
        key = classify(f.label)
        try:
            if key and key in values and values[key] and f.kind in ("text", "textarea"):
                f = find_field(page, f.label, f.kind) or f
                f.locator.fill(values[key])
                report["filled"].append({"label": f.label, "value": values[key][:60], "source": "profile",
                                         "_locator": f.locator, "_full": values[key]})
                continue

            if key and key in values and values[key] and f.kind == "combobox":
                choice = choose_option(page, f, values[key])
                if choice:
                    report["filled"].append({"label": f.label, "value": choice, "source": "profile"})
                    continue
                # no matching option: fall through so an approved answer can try instead

            if key == "cover_letter" and f.kind == "textarea":
                f = find_field(page, f.label, f.kind) or f
                f.locator.fill(app["cover_letter_text"])
                report["filled"].append({"label": f.label, "value": "cover letter text", "source": "generated",
                                         "_locator": f.locator, "_full": app["cover_letter_text"]})
                continue

            if f.kind == "combobox" and CONSENT.search(f.label) and f.required:
                choice = choose_option(page, f, "yes") or choose_option(page, f, "i agree")
                if choice:
                    report["filled"].append({"label": f.label, "value": choice, "source": "consent (required to apply)"})
                    continue

            if f.kind == "select" and CONSENT.search(f.label) and f.required:
                choice = _closest_option("yes", f.options) or next(
                    (o for o in f.options if re.search(r"\b(i )?(agree|accept|acknowledge|consent|yes)\b", o, re.I)), None)
                if choice:
                    f.locator.select_option(label=choice)
                    report["filled"].append({"label": f.label, "value": choice, "source": "consent (required to apply)"})
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
                f = find_field(page, f.label, f.kind) or f
                f.locator.fill(answer)
            elif f.kind == "combobox":
                choice = choose_option(page, f, answer)
                if not choice:
                    if f.required:
                        raise ManualAction(f"Required dropdown I can't answer safely: “{f.label[:100]}”",
                                           {"question": f.label, "answer": answer[:120],
                                            "options": combobox_options(page, f)[0][:15]})
                    report["skipped"].append({"label": f.label, "why": "no matching option"})
                    continue
                report["filled"].append({"label": f.label, "value": choice, "source": f"answer:{key}"})
                continue
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
    audit(page, report, artifacts)
    return report


def audit(page: Page, report: dict, artifacts: Path) -> None:
    """Refuse to submit a form that isn't actually filled correctly.

    Checks the live DOM: every value we wrote must be in the field we meant it for, and no required
    field may be empty. Catches values landing in a neighbouring control after a re-render, and
    required questions that were never answered.
    """
    written = {e["label"].strip().lower(): str(e.get("_full") or e.get("value") or "") for e in report["filled"]}
    misplaced, empty = [], []
    for f in read_form(page):
        if f.kind == "file" or NEVER.search(f.label):
            continue
        shown = current_value(f)
        expected = written.get(f.label.strip().lower())
        if expected:
            if f.kind in ("checkbox", "radio"):
                if shown != "checked":
                    misplaced.append({"field": f.label[:80], "expected": "ticked", "found": "not ticked"})
                continue
            head = expected.strip()[:25].lower()
            if head and head not in shown.lower() and shown.strip()[:25].lower() not in expected.lower():
                misplaced.append({"field": f.label[:80], "expected": expected[:50], "found": shown[:50]})
        elif f.kind in ("checkbox", "radio") and shown == "checked" and " — " in f.label:
            # an option ticked on a multi-option question we did not choose for
            question = f.label.split(" — ")[0].strip().lower()
            if any(k.split(" — ")[0].strip().lower() == question for k in written):
                misplaced.append({"field": f.label[:80], "expected": "not ticked", "found": "ticked"})
        elif f.required and not shown and f.kind != "checkbox":
            empty.append(f.label[:80])
    if misplaced or empty:
        shot(page, artifacts, "audit-failed")
        dump_html(page, artifacts, "audit-failed")
        raise ManualAction(
            "Form did not fill correctly - not submitting. "
            + (f"{len(misplaced)} value(s) in the wrong field. " if misplaced else "")
            + (f"{len(empty)} required field(s) left empty." if empty else ""),
            {"misplaced": misplaced[:6], "empty_required": empty[:8], "report": report})


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


# react-select renders these as list items when a filter matches nothing - they are not choices
PLACEHOLDER = re.compile(r"^(no options|no results|nothing found|loading|type to search|start typing)", re.I)

OPTION_SELECTOR = "[role=option], [class*='select__option'], [class*='Select__option'], li[id*='option']"


def _menu(page: Page, field):
    """The widget's own listbox. Scoping matters: several dropdowns exist in the DOM at once, and an
    unscoped search reads whichever list matches first (e.g. the phone country-code list).
    Matched by attribute, since these ids contain characters CSS selectors can't take (e.g. "[]")."""
    try:
        listbox_id = field.locator.get_attribute("aria-controls")
    except Exception:
        listbox_id = None
    if not listbox_id:
        return None
    menu = page.locator(f'[id="{listbox_id}"]')
    return menu if menu.count() else None


def combobox_options(page: Page, field, query: str = "") -> tuple[list[str], object]:
    """Open the widget (optionally typing `query` to filter) and return (options, menu)."""
    try:
        field.locator.click()
        page.wait_for_timeout(350)
        if query:
            field.locator.fill(query[:40])
            page.wait_for_timeout(700)
        menu = _menu(page, field)
        if menu is None:
            return [], None
        items = menu.locator(OPTION_SELECTOR)
        texts = [t.strip() for t in (items.all_inner_texts() if items.count() else menu.all_inner_texts()) if t.strip()]
        return [t for t in texts if not PLACEHOLDER.match(t)], menu
    except Exception:
        return [], None


def _queries(answer: str) -> list[str]:
    """Filter terms to try: the whole answer, then its most specific parts."""
    a = answer.strip()
    parts = [a, a.split(",")[-1].strip(), a.split(",")[0].strip(), a.split()[0] if a.split() else ""]
    seen, out = set(), []
    for q in parts:
        q = q.strip(" .")
        if q and q.lower() not in seen:
            seen.add(q.lower())
            out.append(q)
    return out[:3]


def _click_option(page: Page, field, menu, choice: str) -> bool:
    """Click an option. Menus vary: some tag items with role=option, some are plain divs, and
    some only respond to keyboard selection."""
    pattern = re.compile(rf"^\s*{re.escape(choice)}\s*$", re.I)
    for target in (menu.locator(OPTION_SELECTOR).filter(has_text=pattern).first,
                   menu.get_by_text(pattern).first):
        try:
            target.click(timeout=3000)
            return True
        except Exception:
            continue
    try:  # keyboard fallback: type the option text and accept the highlighted entry
        field.locator.fill(choice)
        page.wait_for_timeout(600)
        page.keyboard.press("Enter")
        page.wait_for_timeout(300)
        return (field.locator.input_value() or "").strip().lower() == choice.strip().lower() or True
    except Exception:
        return False


def _answer_choice(page: Page, field, answer: str) -> str | None:
    """Apply a yes/no style answer to whatever control type the question uses."""
    try:
        if field.kind == "combobox":
            return choose_option(page, field, answer)
        if field.kind == "select":
            choice = _closest_option(answer, field.options)
            if choice:
                field.locator.select_option(label=choice)
            return choice
        if field.kind in ("radio", "checkbox"):
            # the field carries its own option word; tick it only if it is the answer
            option = (field.options[0] if field.options else field.label).strip().lower()
            if option != answer.strip().lower():
                return None
            fresh = find_field(page, field.label, field.kind) or field  # references go stale as the page re-renders
            fresh.locator.check(timeout=3000)
            page.wait_for_timeout(200)
            check = find_field(page, field.label, field.kind)
            if check and not check.locator.is_checked():
                return None
            return answer
        if field.kind in ("text", "textarea"):
            field.locator.fill(answer)
            return answer
    except Exception:
        return None
    return None


def _selection_stuck(page: Page, field, choice: str) -> bool:
    """Confirm the widget now shows the choice; a click that changed nothing is not a selection."""
    page.wait_for_timeout(400)
    fresh = find_combobox(page, field.label) or field
    shown = current_value(fresh)
    return bool(shown) and not shown.lower().startswith("select") and choice.strip()[:20].lower() in shown.lower()


def choose_option(page: Page, field, answer: str, _retry: bool = True) -> str | None:
    """Pick the option matching `answer`. React dropdowns render few options until you type, so
    each candidate term is tried in turn. Returns None (widget closed) when nothing matches."""
    label = field.label
    try:  # leave whatever the previous field opened, and bring this one into view
        page.keyboard.press("Escape")
        page.wait_for_timeout(150)
    except Exception:
        pass
    field = find_combobox(page, label) or field  # the DOM may have re-rendered since we read it
    try:
        field.locator.scroll_into_view_if_needed(timeout=3000)
    except Exception:
        pass
    for query in ["", *_queries(answer)]:
        options, menu = combobox_options(page, field, query)
        if not options or menu is None:
            continue
        choice = _closest_option(answer, options) or (options[0] if query and len(options) == 1 else None)
        if choice and _click_option(page, field, menu, choice) and _selection_stuck(page, field, choice):
            return choice
    # deterministic matching failed: let the model map the approved answer onto the real options
    options, menu = combobox_options(page, field)
    if menu is not None:
        choice = pick_option(field.label, answer, options)
        if choice and _click_option(page, field, menu, choice) and _selection_stuck(page, field, choice):
            return choice
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass
    if _retry:  # one clean retry: the widget may have re-rendered mid-interaction
        log.info("retrying dropdown %r", label[:60])
        page.wait_for_timeout(600)
        return choose_option(page, field, answer, _retry=False)
    log.warning("no option matched for %r (answer: %r)", label[:60], answer[:40])
    return None


def _closest_option(answer: str, options: list[str]) -> str | None:
    """Pick an option only when the intent is unambiguous."""
    a = answer.strip().lower()
    if not a or not options:
        return None
    for opt in options:  # exact
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

    # option contained in the answer ("Nigeria" for "Lagos, Nigeria")
    contained = [o for o in options if o.strip().lower() in a and len(o.strip()) > 2]
    if len(contained) == 1:
        return contained[0]

    # answer contained in the option ("Nigeria" -> "Nigeria +234")
    holding = [o for o in options if a in o.strip().lower() and len(a) > 2]
    if len(holding) == 1:
        return holding[0]

    # a number in the answer against numeric options ("4+ years" -> "4")
    want = re.search(r"\d+", a)
    if want:
        numeric = [o for o in options if re.fullmatch(r"\D*\d+\D*", o.strip())]
        exact = [o for o in numeric if re.search(r"\d+", o).group(0) == want.group(0)]
        if len(exact) == 1:
            return exact[0]
    return None


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
