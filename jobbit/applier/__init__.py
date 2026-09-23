"""Playwright form fillers, one per ATS.

Contract: every filler either submits the application and returns Submitted, or raises
ManualAction. It must never bypass a CAPTCHA, guess an answer that isn't in the prepared
screening answers, or submit a form it doesn't fully understand.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

log = logging.getLogger(__name__)


class ManualAction(Exception):
    """Submission stopped on purpose; you finish this one by hand."""

    def __init__(self, reason: str, detail: dict | None = None):
        super().__init__(reason)
        self.reason = reason
        self.detail = detail or {}


@dataclass
class Submitted:
    detail: str = "Submitted"
    evidence: dict = field(default_factory=dict)  # screenshot path, confirmation text, final URL


ATS_PATTERNS = {
    # regional domains too: job-boards.eu.greenhouse.io, jobs.eu.lever.co, jobs.eu.ashbyhq.com
    "greenhouse": r"greenhouse\.io",
    "lever": r"lever\.co",
    "ashby": r"ashbyhq\.com",
    "workable": r"apply\.workable\.com",
    "smartrecruiters": r"jobs\.smartrecruiters\.com",
    "workday": r"myworkdayjobs\.com",
    "bamboohr": r"bamboohr\.com/careers",
}

SUPPORTED = {"greenhouse", "lever", "ashby"}  # sites the generic filler understands


def detect_ats(url: str) -> str:
    host_path = f"{urlparse(url).netloc}{urlparse(url).path}"
    for name, pattern in ATS_PATTERNS.items():
        if re.search(pattern, host_path, re.I):
            return name
    return "unknown"


def submit(application: dict, files: dict[str, bytes], artifacts_dir, *,
           no_submit: bool = False, headless: bool = True) -> Submitted:
    """Open this job's form, fill it, and submit. Raises ManualAction if anything is unsafe."""
    from ..profile_parser import parse_profile
    from .browser import browser_page
    from .generic import fill, open_form, submit_form

    job = application["jobs"]
    ats = detect_ats(job["url"])
    if ats not in SUPPORTED:
        raise ManualAction(
            f"No automated filler for {ats} yet" if ats != "unknown"
            else "Unrecognised application site — no automated filler",
            {"ats": ats, "url": job["url"]},
        )

    profile = parse_profile()
    with browser_page(artifacts_dir, headless=headless) as page:
        open_form(page, job["url"], ats, artifacts_dir)
        report = fill(page, profile, application, files, artifacts_dir)
        log.info("filled %d fields, skipped %d, uploaded %d",
                 len(report["filled"]), len(report["skipped"]), len(report["uploaded"]))
        try:
            result = submit_form(page, artifacts_dir, no_submit)
        except ManualAction as e:
            e.detail["report"] = report  # so you can see what was filled before it stopped
            raise
        result.evidence["report"] = report
        result.evidence["ats"] = ats
        return result
