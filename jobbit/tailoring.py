"""Generates the fresh professional summary, tailored resume, and cover letter for one job.

The LLM decides *selection, order, and wording*. Everything factual that doesn't need rewording
(names, contact info, job titles, companies, dates, education, certification names) is rendered from
the parsed profile, never from model output.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

from . import llm
from .models import Job
from .profile_parser import Profile, years_of_experience
from .scoring import FitResult
from .validation import check_text, sentence_count

log = logging.getLogger(__name__)


def _tool(profile: Profile) -> dict:
    return {
        "name": "record_application_documents",
        "description": "Record the tailored summary, resume content, and cover letter.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "2-4 sentences, generated fresh for this JD."},
                "skills": {
                    "type": "array",
                    "description": "Skill groups, most JD-relevant first. Items must be copied verbatim from the profile's Core Skill Categories.",
                    "items": {
                        "type": "object",
                        "properties": {"category": {"type": "string"}, "items": {"type": "array", "items": {"type": "string"}}},
                        "required": ["category", "items"],
                    },
                },
                "certifications_near_top": {"type": "boolean"},
                "certification_order": {
                    "type": "array",
                    "items": {"type": "string", "enum": [c["name"] for c in profile.certifications]},
                },
                "experience": {
                    "type": "array",
                    "description": "Roles in the order they should appear. Omit roles that should be dropped.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {"type": "string", "enum": [e.key for e in profile.experiences]},
                            "bullets": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["key", "bullets"],
                    },
                },
                "cover_letter_body": {
                    "type": "string",
                    "description": "3-4 paragraphs, no greeting/sign-off (added automatically). Paragraphs separated by blank lines.",
                },
            },
            "required": ["summary", "skills", "certifications_near_top", "certification_order", "experience", "cover_letter_body"],
        },
    }


SYSTEM = """You tailor application documents for one candidate. Their complete master profile follows; it is the
ONLY source of truth. Follow its "Professional Summary — GENERATE FRESH PER JOB" rules, its "Tailoring
Guidance" section, and the "Tailoring note" in "Recent / Advanced Work Context" exactly.

Hard rules:
1. Never state any experience, tool, technology, certification, employer, metric, or number that is not in the profile.
   You may reword, reorder, merge, trim, and re-emphasize real facts to mirror the JD's language.
2. The JD may require tools the candidate lacks. Do not claim them. In the cover letter you may note
   transferable experience with a tool the profile does contain.
3. Certifications listed as in progress (GCP Professional Data Engineer, Six Sigma) must never appear as earned.
   Mention them only if relevant, and explicitly as "pursuing".
4. Summary: write it from scratch for this JD. Open with the role type the JD hires for, name AT MOST 3
   skills/tools in total (the most JD-relevant ones), include exactly one real quantified achievement or scope
   indicator suited to the JD's seniority, 2-4 sentences.
5. Experience: use the role keys provided. Recent/Advanced Work Context bullets belong under the Tolaram role
   (key tolaram_africa_group); include or trim them per the Tailoring note and the JD's seniority. Include LFBI
   only when it strengthens a predictive analytics / resource optimization angle.
6. Use the stated years of experience figure; never claim more.
7. Never inflate scope or ownership. Use verbs the profile supports: say "led" only for things the profile says
   were led (e.g. the Data and Analytics Maturity Program); otherwise "built", "designed", "contributed to".
8. Describe a tool as core/primary/daily only if it appears in an Experience or Recent Work bullet. Tools that
   appear only in the skills list may be listed, not emphasized.
9. Plain, specific, confident language. No buzzword filler, no em-dash chains, no invented enthusiasm about company facts not in the JD.

MASTER PROFILE:"""


@dataclass
class TailoredDocs:
    summary: str
    skills: list[dict]
    certifications_near_top: bool
    certification_order: list[str]
    experience: list[dict]
    cover_letter_body: str
    warnings: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return {k: getattr(self, k) for k in
                ("summary", "skills", "certifications_near_top", "certification_order", "experience", "cover_letter_body")}


def tailor(job: Job, fit: FitResult, profile: Profile, cfg: dict) -> TailoredDocs:
    t = cfg["tailoring"]
    years = years_of_experience(t["career_start"])
    if llm.is_stubbed():
        return _stub(profile, years)

    base_prompt = (
        f"Today: {date.today():%B %Y}. Years of experience to state: {years}+.\n"
        f"Assessed JD seniority: {fit.seniority}. Assessed JD focus: {fit.focus}.\n"
        f"Fit rationale: {fit.rationale}\n\n"
        f"Title: {job.title}\nCompany: {job.company}\n\nJob description:\n{job.jd_text[:15000]}"
    )
    prompt, feedback = base_prompt, []
    for attempt in range(t["validation_retries"] + 1):
        out = llm.call_tool(task="tailoring", system=SYSTEM, cached_context=profile.raw_markdown,
                            prompt=prompt, tool=_tool(profile), max_tokens=16000)
        docs = _sanitize(out, profile)
        docs.warnings = validate(docs, profile, job, years)
        if not docs.warnings:
            return docs
        log.warning("attempt %d for %s flagged: %s", attempt + 1, job.title, docs.warnings)
        feedback = docs.warnings
        prompt = (base_prompt + "\n\nA previous draft violated the rules. Fix every issue below by removing or "
                  "rewording the offending content (never by inventing replacements):\n- " + "\n- ".join(feedback))
    return docs  # saved with warnings for manual review


def _sanitize(out: dict, profile: Profile) -> TailoredDocs:
    """Deterministically drop anything that isn't a verbatim profile skill / known role / known cert."""
    known_skills = {s.lower(): s for items in profile.skills.values() for s in items}
    skills = []
    for group in out.get("skills", []):
        items = [known_skills[i.strip().lower()] for i in group.get("items", []) if i.strip().lower() in known_skills]
        if items:
            skills.append({"category": group["category"].strip(), "items": items})
    keys = {e.key for e in profile.experiences}
    cert_names = {c["name"] for c in profile.certifications}
    return TailoredDocs(
        summary=out["summary"].strip(),
        skills=skills,
        certifications_near_top=bool(out.get("certifications_near_top")),
        certification_order=[c for c in out.get("certification_order", []) if c in cert_names] or list(cert_names),
        experience=[e for e in out.get("experience", []) if e.get("key") in keys and e.get("bullets")],
        cover_letter_body=out["cover_letter_body"].strip(),
    )


def validate(docs: TailoredDocs, profile: Profile, job: Job, years: int) -> list[str]:
    issues = []
    n = sentence_count(docs.summary)
    if not 2 <= n <= 4:
        issues.append(f"summary has {n} sentences; must be 2-4")
    allowed = {str(years), f"{years}+"}
    resume_text = "\n".join([docs.summary] + [b for e in docs.experience for b in e["bullets"]])
    issues += [f"resume: {i}" for i in check_text(resume_text, profile.raw_markdown, allowed_numbers=allowed)]
    issues += [f"cover letter: {i}" for i in check_text(docs.cover_letter_body, profile.raw_markdown,
                                                        allowed_numbers=allowed, extra_context=job.jd_text)]
    if not any(e["key"] == profile.experiences[0].key for e in docs.experience):
        issues.append("current role omitted from resume")
    return issues


def _stub(profile: Profile, years: int) -> TailoredDocs:
    return TailoredDocs(
        summary=f"[STUB] Data Engineer with {years}+ years of experience. Set the LLM API key to generate real content.",
        skills=[{"category": k, "items": v} for k, v in profile.skills.items()],
        certifications_near_top=True,
        certification_order=[c["name"] for c in profile.certifications],
        experience=[{"key": e.key, "bullets": e.bullets[:4]} for e in profile.experiences],
        cover_letter_body="[STUB] Cover letter body goes here.\n\nSecond paragraph.",
        warnings=["stubbed output: no LLM API key"],
    )
