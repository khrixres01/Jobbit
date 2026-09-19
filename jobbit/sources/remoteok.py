from ..models import Job
from .base import get_json, html_to_text, parse_date

API = "https://remoteok.com/api"


def fetch(http) -> list[Job]:
    data = get_json(http, API) or []
    jobs = []
    for j in data:
        if "id" not in j:  # first element is a legal notice
            continue
        jobs.append(Job(
            source="remoteok",
            external_id=str(j["id"]),
            title=(j.get("position") or "").strip(),
            company=j.get("company", ""),
            jd_text=html_to_text(j.get("description")),
            url=j.get("apply_url") or j.get("url"),
            posted_date=parse_date(j.get("epoch") or j.get("date")),
            location_text=j.get("location", ""),
            remote=True,  # remote-only board
        ))
    return jobs
