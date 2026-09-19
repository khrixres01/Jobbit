from ..models import Job
from .base import get_json, html_to_text, mentions_remote, parse_date

API = "https://api.lever.co/v0/postings/{token}"


def fetch(http, tokens: list[str]) -> list[Job]:
    jobs = []
    for token in tokens:
        data = get_json(http, API.format(token=token), mode="json")
        if not isinstance(data, list):
            continue
        for p in data:
            cats = p.get("categories") or {}
            location = cats.get("location") or ""
            sections = "\n\n".join(
                f"{s.get('text', '')}\n{html_to_text(s.get('content'))}" for s in p.get("lists", [])
            )
            jd = "\n\n".join(filter(None, [p.get("descriptionPlain"), sections, p.get("additionalPlain")]))
            jobs.append(Job(
                source="lever",
                external_id=p["id"],
                title=p.get("text", "").strip(),
                company=token,
                jd_text=jd,
                url=p.get("applyUrl") or p.get("hostedUrl"),
                posted_date=parse_date(p.get("createdAt")),
                location_text=location,
                remote=p.get("workplaceType") == "remote" or mentions_remote(location),
            ))
    return jobs
