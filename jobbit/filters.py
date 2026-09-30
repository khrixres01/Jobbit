"""Deterministic filters applied before any LLM call. Each returns a discard reason or None."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from .models import Job

_RESTRICTED = re.compile(
    r"\b(us|u\.s\.|usa|united states|north america|americas|canada|uk|united kingdom|"
    r"latam|latin america|apac|australia|india|germany|europe only|eu only|"
    r"us[- ]based|us citizens?|must be located in|est|pst|cst)\b",
    re.I,
)
# Phrases in the JD body that restrict location. Only consulted when location_text is inconclusive.
_JD_RESTRICTED = re.compile(
    r"\b(?:(?:must|should) (?:be|reside|live) (?:based |located |residing )?in|"
    r"(?:legally )?authori[sz]ed to work in|open (?:only )?to candidates (?:based |located )?in|"
    r"only (?:hiring|accepting applications|considering candidates) (?:from|in)|"
    r"(?:remote|position|role)(?: is)? (?:within|in) the)"
    r"\s+(?:the\s+)?(?:us|u\.s\.|usa|united states|canada|uk|united kingdom|europe|eu|latam|latin america|"
    r"australia|india|germany|brazil|mexico)\b"
    r"|\b(?:usa|u\.s\.)[- ]only\b|\bus-only\b",  # bare "us only" would match "join us only if..."
    re.I,
)
_OPEN = re.compile(r"\b(worldwide|anywhere|global|globally|any location|all locations)\b", re.I)
_INCLUDES_NG = re.compile(r"\b(nigeria|africa|emea|lagos|west africa|gmt\+1|wat)\b", re.I)
# Physically in Nigeria (for on-site/hybrid roles, where "EMEA" or "Africa" doesn't mean you can commute).
_IN_NG = re.compile(r"\b(nigeria|lagos|abuja|port harcourt|ibadan)\b", re.I)

# An offer of visa sponsorship or relocation, judged per sentence; a sentence that also negates it
# ("we are unable to sponsor visas", "relocation is not provided") doesn't count.
_SPONSOR = re.compile(
    r"\b(?:visa|work permit|h-?1b|skilled worker)\b[^.\n]{0,25}\bsponsor"
    r"|\bsponsor(?:s|ship|ing)?\b[^.\n]{0,25}\b(?:visas?|work permits?|h-?1b|skilled worker)\b"
    r"|\brelocation (?:assistance|support|package|allowance|bonus|budget|(?:is )?(?:provided|offered|available))"
    r"|\bhelp(?:ing)? (?:you )?relocate\b",
    re.I,
)
_NEGATION = re.compile(r"\b(?:no|not|unable|cannot|can't|won't|don't|doesn't|without|unavailable)\b|n't\b", re.I)


def _words(title: str, terms: list[str]) -> bool:
    # optional trailing "s" so "Data Engineers" matches the term "data engineer"
    return any(re.search(rf"\b{re.escape(t)}s?\b", title, re.I) for t in terms)


def recency(job: Job, max_age_days: int, keep_undated: bool) -> str | None:
    if job.posted_date is None:
        return None if keep_undated else "stale"
    posted = job.posted_date if job.posted_date.tzinfo else job.posted_date.replace(tzinfo=timezone.utc)
    return "stale" if posted < datetime.now(timezone.utc) - timedelta(days=max_age_days) else None


def offers_sponsorship(text: str) -> bool:
    return any(_SPONSOR.search(s) and not _NEGATION.search(s) for s in re.split(r"[.\n]", text or ""))


def in_nigeria(job: Job) -> bool:
    """Located in Nigeria: by location_text, or by the JD's opening when location_text names no place."""
    loc = job.location_text or ""
    return bool(_IN_NG.search(loc) or (not _names_a_place(loc) and _IN_NG.search((job.jd_text or "")[:2000])))


def work_mode(job: Job) -> str | None:
    """Keep remote jobs, any job in Nigeria (on-site and hybrid too), and on-site/hybrid jobs abroad
    that offer visa sponsorship or relocation. Drop other on-site/hybrid jobs abroad."""
    if job.remote or in_nigeria(job) or offers_sponsorship(job.jd_text):
        return None
    return "not_remote"


def has_url(job: Job) -> str | None:
    return None if job.url and job.url.startswith(("http://", "https://")) else "no_url"


def title_keywords(job: Job, include: list[str], exclude: list[str]) -> str | None:
    if _words(job.title, exclude) or not _words(job.title, include):
        return "keyword"
    return None


# Words that say nothing about geography; whatever remains in location_text after removing them is a place.
_NEUTRAL = re.compile(r"\b(remote|remotely|fully|full[- ]time|part[- ]time|hybrid|home|based|work from home|wfh|"
                      r"flexible|distributed|virtual|telecommute|n/?a|none|tbd|or|and|the|in|only|first)\b|[^\w]+", re.I)


def _names_a_place(loc: str) -> bool:
    """'Brazil', 'Remote - Poland', 'Remote, Berlin' -> True. 'Remote', 'Remote (Flexible)', '' -> False."""
    return bool(_NEUTRAL.sub("", loc))


def location_rule(job: Job) -> str:
    """Can the candidate (in Lagos) take this job? Nigeria-located, or offering visa sponsorship/relocation,
    is eligible in any work mode; otherwise the job must be remote and not limited to places excluding
    Nigeria. Keyword classification of location_text, then of restriction phrases in the JD.
    'unknown' is resolved by the LLM scoring call."""
    loc = job.location_text or ""
    if in_nigeria(job) or (job.remote and _INCLUDES_NG.search(loc)):
        return "includes_nigeria"
    if offers_sponsorship(job.jd_text):
        return "visa_sponsorship"
    if not job.remote:
        return "restricted"  # on-site/hybrid abroad without sponsorship: you'd have to already live there
    if _OPEN.search(loc):
        return "worldwide"
    if _RESTRICTED.search(loc) or _names_a_place(loc):
        return "restricted"
    jd = job.jd_text or ""
    if _JD_RESTRICTED.search(jd) and not (_OPEN.search(jd) or _INCLUDES_NG.search(jd)):
        return "restricted"
    return "unknown"


def apply_prefilters(job: Job, cfg: dict) -> str | None:
    f = cfg["filters"]
    for reason in (
        has_url(job),
        work_mode(job),
        recency(job, f["max_age_days"], f["keep_undated"]),
        title_keywords(job, f["title_include"], f["title_exclude"]),
    ):
        if reason:
            return reason
    job.location_eligibility = location_rule(job)
    return "location" if job.location_eligibility == "restricted" else None
