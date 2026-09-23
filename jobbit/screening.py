"""Drafts answers to standard screening questions for one job, for you to edit before applying.

Fact answers come verbatim from config/personal.yaml — never from the model. Only the free-text
answers are generated, and they go through the same fabrication guard as the resume.
"""
from __future__ import annotations

import logging
from functools import lru_cache

import yaml

from . import llm
from .config import ROOT, settings
from .models import Job
from .profile_parser import Profile, years_of_experience
from .validation import check_text

log = logging.getLogger(__name__)


@lru_cache
def personal() -> dict:
    return yaml.safe_load((ROOT / "config" / "personal.yaml").read_text(encoding="utf-8"))


def _tool(keys: list[str]) -> dict:
    return {
        "name": "record_screening_answers",
        "description": "Answer the listed application questions for this job.",
        "input_schema": {
            "type": "object",
            "properties": {
                "answers": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {"type": "string", "enum": keys},
                            "answer": {"type": "string"},
                        },
                        "required": ["key", "answer"],
                    },
                }
            },
            "required": ["answers"],
        },
    }


SYSTEM = """You draft application screening answers for one candidate, from their master profile below.

Rules:
1. Only use facts from the profile. No invented tools, employers, metrics, or numbers.
2. First person, plain and specific. No flattery, no filler, no exclamation marks.
3. Respect each question's word limit. Shorter is better than padded.
4. Say what is true about this candidate and this job; if the JD asks for something they lack, do not
   claim it — point to the closest real experience instead.
5. These are drafts the candidate will edit, so never write a placeholder like [Company] or [X years];
   write the real thing or leave that detail out.
6. State years of experience only as the figure given in the message.
7. Never inflate scope or ownership. Use "led" only where the profile says so (e.g. the Data and Analytics
   Maturity Program); otherwise "built", "designed", "contributed to". Do not add responsibilities the
   profile doesn't state (SLAs, managing people, budgets, on-call) even if the JD mentions them.

MASTER PROFILE:"""


def fact_answer(fact_key: str, profile: Profile) -> str:
    facts = personal().get("facts", {})
    value = str(facts.get(fact_key, "") or "").strip()
    if fact_key == "years_experience" and value.lower() == "auto":
        return f"{years_of_experience(settings()['tailoring']['career_start'])}+ years"
    return value


def draft(job: Job, profile: Profile) -> list[dict]:
    """Return [{key, question, answer, source, edited}]. Unanswerable items get an empty answer."""
    bank = personal().get("bank", [])
    out: list[dict] = []
    generated = [q for q in bank if q.get("kind") == "generated"]
    answers: dict[str, str] = {}

    if generated and not llm.is_stubbed():
        years = years_of_experience(settings()["tailoring"]["career_start"])
        prompt_lines = [f"Title: {job.title}", f"Company: {job.company}",
                        f"Years of experience to state (use this figure, never a different one): {years}+",
                        "", "Questions:"]
        prompt_lines += [f"- {q['key']}: {q['question']} (max {q.get('max_words', 120)} words)" for q in generated]
        prompt_lines += ["", f"Job description:\n{job.jd_text[:12000]}"]
        try:
            res = llm.call_tool(task="tailoring", system=SYSTEM, cached_context=profile.raw_markdown,
                                prompt="\n".join(prompt_lines), tool=_tool([q["key"] for q in generated]),
                                max_tokens=8000)
            answers = {a["key"]: a["answer"].strip() for a in res.get("answers", [])}
        except llm.QuotaExhausted:
            raise
        except Exception:
            log.exception("screening draft failed for %s", job.title)

    for q in bank:
        if q.get("kind") == "fact":
            answer, source = fact_answer(q["fact"], profile), "profile"
        else:
            answer, source = answers.get(q["key"], ""), "ai"
            if answer:
                issues = check_text(answer, profile.raw_markdown, extra_context=job.jd_text)
                if issues:
                    log.warning("screening answer %s flagged: %s", q["key"], issues)
                    source = "ai_flagged"
        out.append({"key": q["key"], "question": q["question"], "answer": answer,
                    "source": source, "edited": False})
    return out


def merge_facts(answers: list[dict], profile: Profile) -> list[dict]:
    """Add fact answers for bank entries added since this application was drafted.

    Facts come verbatim from personal.yaml, so filling them in later is safe; AI answers are
    never back-filled this way (they are job-specific and you approved the ones you have).
    """
    have = {a.get("key") for a in answers}
    out = list(answers)
    for q in personal().get("bank", []):
        if q.get("kind") != "fact" or q["key"] in have:
            continue
        answer = fact_answer(q["fact"], profile)
        if answer:
            out.append({"key": q["key"], "question": q["question"], "answer": answer,
                        "source": "profile", "edited": False})
    return out
