from ..models import Job
from .base import get_json, html_to_text, mentions_remote, parse_date

API = "https://api.ashbyhq.com/posting-api/job-board/{token}"


def fetch(http, tokens: list[str]) -> list[Job]:
    jobs = []
    for token in tokens:
        data = get_json(http, API.format(token=token))
        if not data:
            continue
        for j in data.get("jobs", []):
            if j.get("isListed") is False:
                continue
            location = j.get("location") or ""
            secondary = " ".join(s.get("location", "") for s in j.get("secondaryLocations", []) or [])
            jobs.append(Job(
                source="ashby",
                external_id=f"{token}:{j['id']}",
                title=j.get("title", "").strip(),
                company=token,
                jd_text=j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml")),
                url=j.get("applyUrl") or j.get("jobUrl"),
                posted_date=parse_date(j.get("publishedAt")),
                location_text=" / ".join(filter(None, [location, secondary])),
                remote=bool(j.get("isRemote")) or j.get("workplaceType") == "Remote" or mentions_remote(location),
            ))
    return jobs
