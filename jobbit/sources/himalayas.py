from ..models import Job
from .base import get_json, html_to_text, parse_date

API = "https://himalayas.app/jobs/api"
PAGE_SIZE = 20


def fetch(http, pages: int) -> list[Job]:
    jobs = []
    for page in range(pages):
        data = get_json(http, API, limit=PAGE_SIZE, offset=page * PAGE_SIZE)
        batch = (data or {}).get("jobs", [])
        for j in batch:
            restrictions = j.get("locationRestrictions") or []
            jobs.append(Job(
                source="himalayas",
                external_id=j.get("guid") or j.get("applicationLink"),
                title=(j.get("title") or "").strip(),
                company=j.get("companyName", ""),
                jd_text=html_to_text(j.get("description")),
                url=j.get("applicationLink"),
                posted_date=parse_date(j.get("pubDate")),
                location_text=", ".join(restrictions) if restrictions else "Worldwide",
                remote=True,  # remote-only board
            ))
        if len(batch) < PAGE_SIZE:
            break
    return jobs
