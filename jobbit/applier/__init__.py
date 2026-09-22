"""Playwright form fillers, one per ATS.

Contract: every filler either submits the application and returns Submitted, or raises
ManualAction. It must never bypass a CAPTCHA, guess an answer that isn't in the prepared
screening answers, or submit a form it doesn't fully understand.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse


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
    "greenhouse": r"(boards|job-boards)\.greenhouse\.io|greenhouse\.io/embed",
    "lever": r"jobs\.lever\.co",
    "ashby": r"jobs\.ashbyhq\.com",
    "workable": r"apply\.workable\.com",
    "smartrecruiters": r"jobs\.smartrecruiters\.com",
    "workday": r"myworkdayjobs\.com",
    "bamboohr": r"bamboohr\.com/careers",
}

SUPPORTED: set[str] = set()  # fillers land here as they're built (stage 3)


def detect_ats(url: str) -> str:
    host_path = f"{urlparse(url).netloc}{urlparse(url).path}"
    for name, pattern in ATS_PATTERNS.items():
        if re.search(pattern, host_path, re.I):
            return name
    return "unknown"


def submit(application: dict, files: dict[str, bytes], artifacts_dir) -> Submitted:
    """Dispatch to the filler for this job's ATS."""
    ats = detect_ats(application["jobs"]["url"])
    if ats not in SUPPORTED:
        raise ManualAction(
            f"No automated filler for {ats} yet" if ats != "unknown"
            else "Unrecognised application site — no automated filler",
            {"ats": ats, "url": application["jobs"]["url"]},
        )
    raise ManualAction(f"Filler for {ats} is registered but not implemented", {"ats": ats})
