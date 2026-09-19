from ..models import Job
from .base import get_json, html_to_text, parse_date

API = "https://remotive.com/api/remote-jobs"


def fetch(http, categories: list[str]) -> list[Job]:
    jobs = []
    for cat in categories:
        data = get_json(http, API, category=cat)
        for j in (data or {}).get("jobs", []):
            jobs.append(Job(
                source="remotive",
                external_id=str(j["id"]),
                title=j.get("title", "").strip(),
                company=j.get("company_name", ""),
                jd_text=html_to_text(j.get("description")),
                url=j.get("url"),
                posted_date=parse_date(j.get("publication_date")),
                location_text=j.get("candidate_required_location", ""),
                remote=True,  # remote-only board
            ))
    return jobs
