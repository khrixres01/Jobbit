"""Supabase access for the pipeline (service-role key; bypasses RLS)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from itertools import islice

from supabase import Client, create_client

from .config import secrets, settings
from .models import Job
from .profile_parser import Profile

CHUNK = 150  # keep PostgREST `in` filters well under URL length limits


def _chunks(items, n=CHUNK):
    it = iter(items)
    while batch := list(islice(it, n)):
        yield batch


@lru_cache
def sb() -> Client:
    s = secrets()
    if not (s.supabase_url and s.supabase_key):
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
    return create_client(s.supabase_url, s.supabase_key)


def _start_of_utc_day() -> str:
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


# --------------------------------------------------------------------------- profile
def sync_profile(profile: Profile) -> bool:
    """Upsert the parsed profile if master_profile.md changed. Returns True if updated."""
    current = sb().table("profile").select("source_hash").limit(1).execute().data
    if current and current[0]["source_hash"] == profile.source_hash:
        return False
    sb().table("profile").upsert({"id": True, **profile.to_row(), "parsed_at": datetime.now(timezone.utc).isoformat()}).execute()
    return True


# --------------------------------------------------------------------------- jobs
def filter_new(jobs: list[Job]) -> list[Job]:
    """Drop jobs already in the DB, by (source, external_id) or cross-source dedupe_key."""
    seen_keys, seen_ids = set(), set()
    for batch in _chunks([j.dedupe_key for j in jobs]):
        rows = sb().table("jobs").select("dedupe_key").in_("dedupe_key", batch).execute().data
        seen_keys.update(r["dedupe_key"] for r in rows)
    for batch in _chunks([j.external_id for j in jobs]):
        rows = sb().table("jobs").select("source,external_id").in_("external_id", batch).execute().data
        seen_ids.update((r["source"], r["external_id"]) for r in rows)
    return [j for j in jobs if j.dedupe_key not in seen_keys and (j.source, j.external_id) not in seen_ids]


def insert_jobs(jobs: list[Job]) -> int:
    inserted = 0
    for batch in _chunks(jobs, 100):
        rows = sb().table("jobs").upsert(
            [j.to_row() for j in batch], on_conflict="dedupe_key", ignore_duplicates=True
        ).execute().data
        inserted += len(rows)
    return inserted


def _row_to_job(r: dict) -> Job:
    from .sources.base import parse_date

    return Job(
        id=r["id"], source=r["source"], external_id=r["external_id"], title=r["title"], company=r["company"],
        jd_text=r["jd_text"], url=r["url"], posted_date=parse_date(r["posted_date"]),
        location_text=r["location_text"] or "", remote=r["remote"],
        location_eligibility=r["location_eligibility"], fit_score=r["fit_score"], fit_rationale=r["fit_rationale"],
    )


def jobs_to_score(limit: int) -> list[Job]:
    """Kept, unscored jobs still within the recency window, newest first. Includes backlog from earlier runs."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=settings()["filters"]["max_age_days"])).isoformat()
    rows = (sb().table("jobs").select("*")
            .is_("discard_reason", "null").is_("scored_at", "null").gte("ingested_at", cutoff)
            .order("posted_date", desc=True, nullsfirst=False).limit(limit).execute().data)
    return [_row_to_job(r) for r in rows]


def jobs_to_tailor(threshold: int, limit: int) -> list[Job]:
    """Scored at/above threshold, not discarded, and no application yet. Highest score first."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=settings()["filters"]["max_age_days"])).isoformat()
    rows = (sb().table("jobs").select("*, applications(id)")
            .is_("discard_reason", "null").gte("fit_score", threshold).gte("scored_at", cutoff)
            .order("fit_score", desc=True).limit(limit * 3).execute().data)
    return [_row_to_job(r) for r in rows if not r.get("applications")][:limit]


def save_score(job: Job) -> None:
    sb().table("jobs").update({
        "fit_score": job.fit_score, "fit_rationale": job.fit_rationale,
        "location_eligibility": job.location_eligibility, "discard_reason": job.discard_reason,
        "scored_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", job.id).execute()


def discard(job_id: str, reason: str) -> None:
    sb().table("jobs").update({"discard_reason": reason}).eq("id", job_id).execute()


def scores_today() -> int:
    return sb().table("jobs").select("id", count="exact").gte("scored_at", _start_of_utc_day()).limit(1).execute().count or 0


def tailors_today() -> int:
    return sb().table("applications").select("id", count="exact").gte("created_at", _start_of_utc_day()).limit(1).execute().count or 0


# --------------------------------------------------------------------------- applications
def upload(path: str, data: bytes, content_type: str) -> str:
    bucket = settings()["storage"]["bucket"]
    sb().storage.from_(bucket).upload(path, data, {"content-type": content_type, "upsert": "true"})
    return path


def insert_application(row: dict) -> None:
    sb().table("applications").insert(row).execute()
    sb().table("application_events").insert({
        "application_id": row["id"], "event": "created",
        "detail": {"fit_score": row["fit_score"], "warnings": len(row["validation_warnings"])},
    }).execute()


def pending_review_count() -> int:
    return (sb().table("applications").select("id", count="exact")
            .eq("status", "pending_review").limit(1).execute().count or 0)


# --------------------------------------------------------------------------- runs
def start_run(workflow: str) -> int:
    return sb().table("pipeline_runs").insert({"workflow": workflow}).execute().data[0]["id"]


def finish_run(run_id: int, stats: dict, error: str | None = None) -> None:
    sb().table("pipeline_runs").update({
        "finished_at": datetime.now(timezone.utc).isoformat(), "stats": stats, "error": error,
    }).eq("id", run_id).execute()


# --------------------------------------------------------------------------- workflow 2
def get_application(application_id: str) -> dict | None:
    rows = (sb().table("applications").select("*, jobs(*)")
            .eq("id", application_id).limit(1).execute().data)
    return rows[0] if rows else None


def set_application_status(application_id: str, status: str, detail: str | None = None) -> None:
    sb().table("applications").update({"status": status, "status_detail": detail}).eq("id", application_id).execute()


def add_event(application_id: str, event: str, detail: dict | None = None) -> None:
    sb().table("application_events").insert(
        {"application_id": application_id, "event": event, "detail": detail or {}}).execute()


def download(path: str) -> bytes:
    return sb().storage.from_(settings()["storage"]["bucket"]).download(path)
