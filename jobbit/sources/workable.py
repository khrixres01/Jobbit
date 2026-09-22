from ..models import Job
from .base import get_json, html_to_text, mentions_remote, parse_date

API = "https://apply.workable.com/api/v1/widget/accounts/{token}"


def fetch(http, tokens: list[str]) -> list[Job]:
    jobs = []
    for token in tokens:
        data = get_json(http, API.format(token=token), details="true")
        if not data:
            continue
        company = data.get("name") or token
        for j in data.get("jobs", []):
            location = ", ".join(filter(None, [j.get("city"), j.get("state"), j.get("country")]))
            jobs.append(Job(
                source="workable",
                external_id=f"{token}:{j['shortcode']}",
                title=(j.get("title") or "").strip(),
                company=company,
                jd_text=html_to_text(j.get("description")),
                url=j.get("application_url") or j.get("url"),
                posted_date=parse_date(j.get("published_on") or j.get("created_at")),
                location_text=location,
                remote=bool(j.get("telecommuting")) or mentions_remote(location, j.get("title")),
            ))
    return jobs
