from ..models import Job
from .base import get_json, html_to_text, mentions_remote, parse_date

API = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"


def fetch(http, tokens: list[str]) -> list[Job]:
    jobs = []
    for token in tokens:
        data = get_json(http, API.format(token=token), content="true")
        if not data:
            continue
        company = data.get("meta", {}).get("company_name") or token  # meta is not always present
        for j in data.get("jobs", []):
            location = (j.get("location") or {}).get("name", "")
            office_names = " ".join(o.get("name", "") for o in j.get("offices", []))
            jobs.append(Job(
                source="greenhouse",
                external_id=f"{token}:{j['id']}",
                title=j.get("title", "").strip(),
                company=j.get("company_name") or company,
                jd_text=html_to_text(j.get("content")),
                url=j.get("absolute_url"),
                posted_date=parse_date(j.get("first_published") or j.get("updated_at")),
                location_text=location,
                remote=mentions_remote(location, office_names, j.get("title")),
            ))
    return jobs
