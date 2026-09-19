import feedparser

from ..models import Job
from .base import html_to_text, parse_date


def fetch(http, feeds: list[str]) -> list[Job]:
    jobs, seen = [], set()
    for url in feeds:
        r = http.get(url, headers={"Accept": "application/rss+xml"})
        r.raise_for_status()
        for e in feedparser.parse(r.content).entries:
            if e.link in seen:
                continue
            seen.add(e.link)
            # titles look like "Company: Job Title"
            company, sep, title = e.title.partition(":")
            jobs.append(Job(
                source="weworkremotely",
                external_id=e.get("id") or e.link,
                title=(title if sep else e.title).strip(),
                company=company.strip() if sep else "",
                jd_text=html_to_text(e.get("summary") or e.get("description")),
                url=e.link,
                posted_date=parse_date(e.get("published")),
                location_text=e.get("region", ""),
                remote=True,  # remote-only board
            ))
    return jobs
