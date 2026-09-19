from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


@dataclass
class Job:
    source: str
    external_id: str
    title: str
    company: str
    jd_text: str
    url: str | None
    posted_date: datetime | None
    location_text: str = ""
    remote: bool = False
    # set during the pipeline
    location_eligibility: str = "unknown"
    fit_score: int | None = None
    fit_rationale: str | None = None
    discard_reason: str | None = None
    id: str | None = field(default=None, repr=False)

    @property
    def dedupe_key(self) -> str:
        raw = f"{_norm(self.company)}|{_norm(self.title)}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def to_row(self) -> dict:
        return {
            "source": self.source,
            "external_id": self.external_id,
            "dedupe_key": self.dedupe_key,
            "title": self.title,
            "company": self.company,
            "location_text": self.location_text or None,
            "jd_text": self.jd_text,
            "url": self.url or "",
            "posted_date": self.posted_date.isoformat() if self.posted_date else None,
            "remote": self.remote,
            "location_eligibility": self.location_eligibility,
            "fit_score": self.fit_score,
            "fit_rationale": self.fit_rationale,
            "discard_reason": self.discard_reason,
        }
