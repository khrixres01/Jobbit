"""Workflow 1: scrape -> filter -> score -> tailor -> write to Supabase -> notify.

    python -m jobbit.workflow1              # full run (needs Supabase + Anthropic keys)
    python -m jobbit.workflow1 --dry-run    # no DB writes; stubbed LLM if no key; docs saved to ./out
"""
from __future__ import annotations

import argparse
import logging
import re
import uuid
from collections import Counter

from . import db, documents, llm, notify
from .config import ROOT, secrets, settings
from .filters import apply_prefilters, recency
from .models import Job
from .profile_parser import Profile, parse_profile
from .scoring import score
from .sources import fetch_all
from .tailoring import tailor

log = logging.getLogger("jobbit.workflow1")


def dedupe_batch(jobs: list[Job]) -> list[Job]:
    seen, out = set(), []
    for j in jobs:
        if j.dedupe_key in seen or not j.title:
            continue
        seen.add(j.dedupe_key)
        out.append(j)
    return out


def score_job(job: Job, profile: Profile, cfg: dict):
    """Scores in place and sets discard_reason when the job shouldn't proceed."""
    fit = score(job, profile)
    job.fit_score, job.fit_rationale = fit.fit_score, fit.rationale
    # Keyword rules are authoritative when they found something; the LLM fills in 'unknown'.
    if job.location_eligibility == "unknown":
        job.location_eligibility = fit.location_eligibility
    if job.location_eligibility == "restricted":
        job.discard_reason = "location"
    elif job.fit_score < cfg["scoring"]["threshold"]:
        job.discard_reason = "below_threshold"
    return fit


def build_application(job: Job, profile: Profile, cfg: dict, fit) -> tuple[dict, dict]:
    docs = tailor(job, fit, profile, cfg)
    files = documents.render_all(docs, profile, job)
    app_id = str(uuid.uuid4())
    row = {
        "id": app_id,
        "job_id": job.id,
        "fit_score": job.fit_score,
        "rationale": job.fit_rationale,
        "generated_summary_text": docs.summary,
        "tailored_resume_text": files["resume_text"],
        "tailored_resume_json": docs.to_json(),
        "cover_letter_text": files["cover_text"],
        "validation_warnings": docs.warnings,
        "status": "pending_review",
    }
    return row, files


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]


# ----------------------------------------------------------------------------- dry run
def dry_run(limit: int) -> None:
    cfg, profile = settings(), parse_profile()
    log.info("dry run (%s %s)", "STUBBED" if llm.is_stubbed() else "REAL", llm.provider())
    jobs, per_source = fetch_all()
    jobs = dedupe_batch(jobs)
    for j in jobs:
        j.discard_reason = apply_prefilters(j, cfg)
    log.info("fetched per source: %s", per_source)
    log.info("prefilter outcome: %s", dict(Counter(j.discard_reason or "kept" for j in jobs)))

    kept = sorted((j for j in jobs if j.discard_reason is None),
                  key=lambda j: j.posted_date.timestamp() if j.posted_date else 0, reverse=True)[:limit]
    out_dir = ROOT / "out"
    for j in kept:
        try:
            fit = score_job(j, profile, cfg)
        except llm.QuotaExhausted as e:
            log.warning("stopping: %s", e)
            return
        log.info("%3s  %-10s %s @ %s  [%s] %s", j.fit_score, j.source, j.title, j.company,
                 j.location_eligibility, j.discard_reason or "")
        if j.discard_reason:
            continue
        try:
            row, files = build_application(j, profile, cfg, fit)
        except llm.QuotaExhausted as e:
            log.warning("stopping: %s", e)
            return
        d = out_dir / f"{_slug(j.company)}-{_slug(j.title)}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "resume.pdf").write_bytes(files["resume_pdf"])
        (d / "resume.docx").write_bytes(files["resume_docx"])
        (d / "resume.txt").write_text(files["resume_text"], encoding="utf-8")
        (d / "cover_letter.pdf").write_bytes(files["cover_pdf"])
        (d / "cover_letter.docx").write_bytes(files["cover_docx"])
        (d / "cover_letter.txt").write_text(files["cover_text"], encoding="utf-8")
        (d / "warnings.txt").write_text("\n".join(row["validation_warnings"]) or "none", encoding="utf-8")
        log.info("     wrote %s", d.relative_to(ROOT))


# ----------------------------------------------------------------------------- real run
def run() -> dict:
    cfg, profile = settings(), parse_profile()
    if llm.is_stubbed():
        raise SystemExit(f"No API key for provider {llm.provider()!r}. Use --dry-run, or add the key to persist results.")
    stats: dict = {}
    run_id = db.start_run("scrape")
    try:
        stats["profile_updated"] = db.sync_profile(profile)

        # 1. fetch + dedupe
        jobs, stats["fetched"] = fetch_all()
        jobs = db.filter_new(dedupe_batch(jobs))
        stats["new"] = len(jobs)

        # 2. deterministic filters; every new job is stored so it's never re-evaluated
        for j in jobs:
            j.discard_reason = apply_prefilters(j, cfg)
        stats["prefilter"] = dict(Counter(j.discard_reason or "kept" for j in jobs))
        stats["inserted"] = db.insert_jobs(jobs)

        # 3. score (new + backlog), bounded by per-run and per-day caps
        sc = cfg["scoring"]
        budget = max(0, min(sc["max_scores_per_run"], sc["max_scores_per_day"] - db.scores_today()))
        scored, fits = Counter(), {}
        f = cfg["filters"]
        for j in db.jobs_to_score(budget):
            if recency(j, f["max_age_days"], f["keep_undated"]):
                db.discard(j.id, "stale")
                continue
            try:
                fits[j.id] = score_job(j, profile, cfg)
            except llm.QuotaExhausted as e:
                log.warning("scoring stopped: %s (remaining jobs wait for the next run)", e)
                scored["quota_stop"] += 1
                break
            except Exception:
                log.exception("scoring failed for %s", j.id)
                scored["error"] += 1
                continue
            db.save_score(j)
            scored[j.discard_reason or "above_threshold"] += 1
        stats["scoring"] = dict(scored)

        # 4. tailor + documents + applications
        tc = cfg["tailoring"]
        budget = max(0, min(tc["max_tailors_per_run"], tc["max_tailors_per_day"] - db.tailors_today()))
        created = failed = 0
        for j in db.jobs_to_tailor(sc["threshold"], budget):
            try:
                fit = fits.get(j.id) or _fit_from_row(j)
                row, files = build_application(j, profile, cfg, fit)
                base = row["id"]
                row["tailored_resume_file_url"] = db.upload(f"{base}/resume.pdf", files["resume_pdf"], "application/pdf")
                row["tailored_resume_docx_url"] = db.upload(f"{base}/resume.docx", files["resume_docx"], DOCX)
                row["cover_letter_file_url"] = db.upload(f"{base}/cover_letter.pdf", files["cover_pdf"], "application/pdf")
                row["cover_letter_docx_url"] = db.upload(f"{base}/cover_letter.docx", files["cover_docx"], DOCX)
                db.insert_application(row)
                created += 1
            except llm.QuotaExhausted as e:
                log.warning("tailoring stopped: %s (remaining jobs wait for the next run)", e)
                stats["tailor_quota_stop"] = True
                break
            except Exception:
                log.exception("tailoring failed for job %s", j.id)
                db.discard(j.id, "tailor_failed")  # visible in DB; clear discard_reason to retry
                failed += 1
        stats["applications_created"], stats["tailor_failed"] = created, failed

        # 5. notify
        if created:
            pending = db.pending_review_count()
            notify.telegram(f"📋 {created} new application{'s' if created != 1 else ''} ready to review "
                            f"({pending} pending total)\n{secrets().dashboard_url}")
        db.finish_run(run_id, stats)
        return stats
    except Exception as e:
        db.finish_run(run_id, stats, error=repr(e))
        raise


DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _fit_from_row(j: Job):
    """Backlog jobs scored in an earlier run: rebuild a FitResult from stored fields, no extra LLM call."""
    from .scoring import FitResult

    return FitResult(fit_score=j.fit_score, rationale=j.fit_rationale or "", location_eligibility=j.location_eligibility,
                     seniority="unknown (infer from JD)", focus="infer from JD")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=5, help="dry run: max jobs to score")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if args.dry_run:
        dry_run(args.limit)
    else:
        log.info("run stats: %s", run())


if __name__ == "__main__":
    main()
