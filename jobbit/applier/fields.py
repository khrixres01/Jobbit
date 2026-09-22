"""Reads a form, works out what each field is asking, and decides what (if anything) may go in it.

Rules that keep this honest:
- Identity fields come from the master profile; screening questions come only from the answers you
  approved on the dashboard.
- A required field we can't match confidently raises ManualAction — nothing is invented.
- Demographic / EEOC questions are never answered.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from playwright.sync_api import Locator, Page

from .. import llm
from ..profile_parser import Profile
from ..screening import personal

log = logging.getLogger(__name__)

# label text -> profile value key
IDENTITY = [
    ("first_name", r"\bfirst name\b|\bgiven name\b"),
    ("last_name", r"\blast name\b|\bsurname\b|\bfamily name\b"),
    ("full_name", r"^\s*(full )?name\b|\byour name\b"),
    ("email", r"\be-?mail\b"),
    ("phone", r"\bphone\b|\bmobile\b|\btelephone\b"),
    ("linkedin", r"\blinkedin\b"),
    ("github", r"\bgithub\b"),
    ("website", r"\bwebsite\b|\bportfolio\b|\bpersonal site\b|\bother url\b"),
    ("country", r"\bcountry\b"),
    ("location", r"\blocation\b|\bcity\b|\bwhere are you based\b|\bcurrent residence\b"),
    ("company", r"\bcurrent (company|employer)\b"),
    ("resume", r"\bresum[ée]\b|\bcv\b"),
    ("cover_letter", r"\bcover letter\b"),
]

NEVER = re.compile(
    r"\b(gender|race|ethnic|hispanic|latino|veteran|disability|disabled|sexual orientation|"
    r"pronoun|age range|date of birth|criminal|conviction|felony|background check|"
    r"self-?identif|eeo|equal (employment )?opportunity|voluntary (self-)?disclosure)\b", re.I)

CONSENT = re.compile(r"\b(privacy (policy|notice)|terms|consent|gdpr|data processing|acknowledge|i agree|i confirm)\b", re.I)


@dataclass
class Field:
    locator: Locator
    kind: str          # text | textarea | select | checkbox | radio | file
    label: str
    required: bool
    options: list[str]
    name: str


def profile_values(profile: Profile) -> dict[str, str]:
    c = profile.contact
    full = c.get("name", "")
    first, _, last = full.partition(" ")
    facts = personal().get("facts", {})
    return {
        "first_name": first, "last_name": last, "full_name": full,
        "email": c.get("email", ""), "phone": c.get("phone", ""),
        "linkedin": c.get("linkedin", ""), "github": c.get("github", ""),
        "website": c.get("github", ""), "location": facts.get("location") or c.get("location", ""),
        "country": facts.get("country", ""),
        "company": profile.experiences[0].company if profile.experiences else "",
    }


def label_for(page: Page, el: Locator) -> str:
    """Best-effort visible question text for a control."""
    try:
        text = el.evaluate(
            """el => {
                const byFor = el.id ? document.querySelector(`label[for="${CSS.escape(el.id)}"]`) : null;
                const wrap = el.closest('label');
                const aria = el.getAttribute('aria-label');
                const described = el.getAttribute('aria-labelledby');
                const byId = described ? document.getElementById(described.split(' ')[0]) : null;
                const group = el.closest('fieldset, .field, [class*="field"], [class*="question"], [class*="Question"]');
                const legend = group ? group.querySelector('legend, label, .label, [class*="label"]') : null;
                const parts = [byFor?.innerText, wrap?.innerText, aria, byId?.innerText, legend?.innerText,
                               el.getAttribute('placeholder'), el.getAttribute('name')];
                return (parts.find(p => p && p.trim()) || '').trim();
            }"""
        ) or ""
    except Exception:
        text = ""
    return re.sub(r"\s+", " ", text).strip()[:300]


def read_form(page: Page, root: str = "form, [class*='application'], body") -> list[Field]:
    fields: list[Field] = []
    seen_radio_groups: set[str] = set()
    container = page.locator(root).first
    controls = container.locator("input:not([type=hidden]), textarea, select")
    for i in range(min(controls.count(), 120)):
        el = controls.nth(i)
        try:
            if not el.is_visible():
                continue
            tag = el.evaluate("e => e.tagName.toLowerCase()")
            input_type = (el.get_attribute("type") or "text").lower()
            name = el.get_attribute("name") or el.get_attribute("id") or ""
            if input_type in ("submit", "button", "reset", "image"):
                continue
            kind = ("file" if input_type == "file" else "checkbox" if input_type == "checkbox"
                    else "radio" if input_type == "radio" else "select" if tag == "select"
                    else "textarea" if tag == "textarea" else "text")
            if kind == "radio":
                if name in seen_radio_groups:
                    continue
                seen_radio_groups.add(name)
            options = []
            if kind == "select":
                options = [o.strip() for o in el.locator("option").all_inner_texts() if o.strip()]
            elif kind == "radio" and name:
                options = [t.strip() for t in container.locator(f"input[name='{name}']").evaluate_all(
                    "els => els.map(e => (e.closest('label')?.innerText) || e.value || '')") if t.strip()]
            required = bool(el.get_attribute("required") or el.get_attribute("aria-required") == "true")
            label = label_for(page, el)
            if not required and label:
                required = bool(re.search(r"\*\s*$|\(required\)", label, re.I))
            fields.append(Field(el, kind, label, required, options, name))
        except Exception:
            continue
    return fields


def classify(label: str) -> str | None:
    text = label.lower()
    for key, pattern in IDENTITY:
        if re.search(pattern, text):
            return key
    return None


MAP_TOOL = {
    "name": "map_questions",
    "description": "Map each form question to one of the candidate's prepared answers, or to none.",
    "input_schema": {
        "type": "object",
        "properties": {
            "mappings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer"},
                        "answer_key": {"type": "string", "description": "prepared answer key, or 'none'"},
                        "confidence": {"type": "string", "enum": ["high", "low"]},
                    },
                    "required": ["index", "answer_key", "confidence"],
                },
            }
        },
        "required": ["mappings"],
    },
}

MAP_SYSTEM = """You match job-application form questions to a candidate's prepared answers.
Return 'none' unless the prepared answer genuinely answers the question — a wrong match puts false
information on a real application. Use 'high' confidence only when the question is asking for the same
thing as the prepared answer. Never map demographic or equal-opportunity questions."""


def map_questions(questions: list[str], answers: list[dict]) -> dict[int, str]:
    """{question index: answer key} for confident matches only."""
    if not questions or llm.is_stubbed():
        return {}
    keys = [a["key"] for a in answers if (a.get("answer") or "").strip()]
    if not keys:
        return {}
    listing = "\n".join(f"{a['key']}: {a['question']}" for a in answers if a["key"] in keys)
    asked = "\n".join(f"{i}: {q}" for i, q in enumerate(questions))
    try:
        out = llm.call_tool(task="scoring", system=MAP_SYSTEM,
                            cached_context=f"PREPARED ANSWERS:\n{listing}",
                            prompt=f"Form questions:\n{asked}", tool=MAP_TOOL, max_tokens=3000)
    except Exception:
        log.exception("question mapping failed")
        return {}
    return {m["index"]: m["answer_key"] for m in out.get("mappings", [])
            if m.get("confidence") == "high" and m.get("answer_key") in keys}
