"""Fit scoring (0-100) + location eligibility + job-type classification via the configured LLM."""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import llm
from .models import Job
from .config import settings
from .profile_parser import Profile, years_of_experience

FOCUS_TYPES = ["fabric_azure_data_engineering", "analytics_bi", "devops_infra", "ml_predictive",
               "governance_platform_leadership", "general_data_engineering", "other"]
SENIORITY = ["junior", "mid", "senior", "lead"]

SCORE_TOOL = {
    "name": "record_fit",
    "description": "Record how well the candidate fits this job.",
    "input_schema": {
        "type": "object",
        "properties": {
            "fit_score": {"type": "integer", "minimum": 0, "maximum": 100},
            "rationale": {"type": "string", "description": "2-3 sentences: strongest matches and key gaps."},
            "location_eligibility": {"type": "string", "enum": ["worldwide", "includes_nigeria", "restricted", "unknown"]},
            "seniority": {"type": "string", "enum": SENIORITY},
            "focus": {"type": "string", "enum": FOCUS_TYPES},
        },
        "required": ["fit_score", "rationale", "location_eligibility", "seniority", "focus"],
    },
}

SYSTEM = """You screen remote job postings for one candidate, whose complete master profile follows.
Score fit 0-100 using ONLY facts in the profile:
- 85-100: core requirements met with direct experience; seniority matches.
- 70-84: most requirements met; minor gaps or adjacent tools.
- 50-69: partial match; notable gaps in required skills or seniority.
- 0-49: different discipline or hard requirements clearly unmet.
Required skills the profile lacks count heavily; nice-to-haves count lightly. Check the WHOLE profile,
including Core Skill Categories, before calling a skill missing. Use the experience figure given in the message.
The candidate lives in Lagos, Nigeria. location_eligibility:
- worldwide: open to any country
- includes_nigeria: explicitly includes Nigeria, Africa, or EMEA
- restricted: limited to countries/regions/timezones excluding Nigeria, or requires work authorization elsewhere (e.g. US-only)
- unknown: the posting doesn't say
seniority is the level the JD hires for. focus is the JD's primary emphasis.

MASTER PROFILE:"""


@dataclass
class FitResult:
    fit_score: int
    rationale: str
    location_eligibility: str
    seniority: str
    focus: str


def score(job: Job, profile: Profile) -> FitResult:
    if llm.is_stubbed():
        return _stub(job, profile)
    years = years_of_experience(settings()["tailoring"]["career_start"])
    prompt = (f"Candidate's total professional experience: {years}+ years.\n"
              f"Title: {job.title}\nCompany: {job.company}\nLocation: {job.location_text or 'not stated'}\n\n"
              f"Job description:\n{job.jd_text[:15000]}")
    out = llm.call_tool(task="scoring", system=SYSTEM, cached_context=profile.raw_markdown,
                        prompt=prompt, tool=SCORE_TOOL, max_tokens=4000)  # Gemini counts thinking tokens here
    return FitResult(
        fit_score=max(0, min(100, int(out["fit_score"]))),
        rationale=out["rationale"].strip(),
        location_eligibility=out["location_eligibility"],
        seniority=out["seniority"],
        focus=out["focus"],
    )


def _stub(job: Job, profile: Profile) -> FitResult:
    """Keyword-overlap heuristic so the pipeline can run end-to-end without an API key."""
    skills = {s.lower() for items in profile.skills.values() for s in items}
    text = f"{job.title} {job.jd_text}".lower()
    hits = sorted(s for s in skills if re.search(rf"\b{re.escape(s)}\b", text))
    return FitResult(
        fit_score=min(100, 40 + 6 * len(hits)),
        rationale=f"[STUB] keyword overlap: {', '.join(hits[:8]) or 'none'}",
        location_eligibility=job.location_eligibility,
        seniority="mid",
        focus="fabric_azure_data_engineering" if "fabric" in text or "azure" in text else "general_data_engineering",
    )
