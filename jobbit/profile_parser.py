"""Parses profile/master_profile.md into structured data.

The markdown file is the source of truth; this structure is used for rendering documents
(names, dates, companies are never taken from LLM output) and for the fabrication guard.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from datetime import date

from .config import PROFILE_PATH


@dataclass
class Experience:
    key: str
    title: str
    company: str
    location: str
    dates: str
    bullets: list[str]
    keywords: str


@dataclass
class Profile:
    source_hash: str
    raw_markdown: str
    contact: dict[str, str]
    skills: dict[str, list[str]]
    certifications: list[dict[str, str]]
    education: list[str]
    experiences: list[Experience]
    advanced_context: list[str]
    achievements: list[str]
    summary_rules: str
    tailoring_guidance: str

    def to_row(self) -> dict:
        row = asdict(self)
        row["experiences"] = [asdict(e) for e in self.experiences]
        return row


def _sections(md: str, level: int) -> dict[str, str]:
    """Split markdown on headings of exactly `level` hashes."""
    pattern = re.compile(rf"^{'#' * level} (?!#)(.+)$", re.M)
    matches = list(pattern.finditer(md))
    out = {}
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(md)
        out[m.group(1).strip()] = md[m.end():end].strip()
    return out


def _find(sections: dict[str, str], prefix: str) -> str:
    for name, body in sections.items():
        if name.lower().startswith(prefix.lower()):
            return body
    raise ValueError(f"master_profile.md is missing a section starting with '{prefix}'")


def _bullets(body: str) -> list[str]:
    return [re.sub(r"^[-*]\s+", "", line).strip() for line in body.splitlines() if re.match(r"^\s*[-*]\s+", line)]


def _strip_md(s: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"\1", s)


def parse_profile(md: str | None = None) -> Profile:
    md = md if md is not None else PROFILE_PATH.read_text(encoding="utf-8")
    h2 = _sections(md, 2)

    contact = {}
    for b in _bullets(_find(h2, "Contact")):
        k, _, v = b.partition(":")
        contact[k.strip().lower().replace(" ", "_")] = v.strip()

    skills = {}
    for b in _bullets(_find(h2, "Core Skill Categories")):
        m = re.match(r"\*\*(.+?):\*\*\s*(.+)", b)
        if m:
            skills[m.group(1).strip()] = [s.strip() for s in re.split(r",\s*(?![^()]*\))", m.group(2))]  # keep "Azure (Data Factory, Synapse)" whole

    certifications = []
    for b in _bullets(_find(h2, "Certifications")):
        parts = [p.strip() for p in b.split("—")]
        certifications.append({
            "name": parts[0],
            "issuer": parts[1] if len(parts) == 3 else "",
            "date": parts[-1] if len(parts) > 1 else "",
        })

    experiences = []
    for heading, body in _sections(_find(h2, "Experience"), 3).items():
        role_part, _, dates = heading.partition("|")
        title, _, org = role_part.rpartition("—")  # rpartition: "Data Analyst — Volunteer — LFBI"
        company, _, loc = org.partition("(")
        kw = re.search(r"\*\*Keywords this role covers well:\*\*\s*(.+)", body)
        experiences.append(Experience(
            key=re.sub(r"[^a-z0-9]+", "_", company.strip().lower()).strip("_"),
            title=title.strip(),
            company=company.strip(),
            location=loc.rstrip(") ").strip(),
            dates=dates.strip(),
            bullets=_bullets(body.split("**Keywords")[0]),
            keywords=kw.group(1).strip() if kw else "",
        ))

    advanced = _find(h2, "Recent / Advanced Work Context")
    summary_body = _find(h2, "Professional Summary")

    return Profile(
        source_hash=hashlib.sha256(md.encode()).hexdigest(),
        raw_markdown=md,
        contact=contact,
        skills=skills,
        certifications=certifications,
        education=_bullets(_find(h2, "Education")),
        experiences=experiences,
        advanced_context=[_strip_md(b) for b in _bullets(advanced.split("**Tailoring note:**")[0])],
        achievements=_bullets(_find(h2, "Notable Quantified Achievements")),
        summary_rules=summary_body,
        tailoring_guidance=_find(h2, "Tailoring Guidance"),
    )


def years_of_experience(career_start: str, today: date | None = None) -> int:
    """Whole years since career_start ('YYYY-MM'), rounded down. Used as 'N+ years'."""
    today = today or date.today()
    y, m = (int(x) for x in str(career_start).split("-"))
    months = (today.year - y) * 12 + (today.month - m)
    return max(months // 12, 0)
