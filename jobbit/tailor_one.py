"""Tailor a single job on demand, triggered by a "Tailor this job" click in the dashboard.

    python -m jobbit.tailor_one --job <uuid>

Loads one already-scored job, generates its tailored resume + cover letter, stores them, and
clears the job's tailor_requested flag. Fast path for a job you want to apply to right now,
instead of waiting for the next full scrape run. Never submits anything.
"""
from __future__ import annotations

import argparse
import logging

from . import db, llm, notify
from .config import secrets, settings
from .filters import location_rule
from .profile_parser import parse_profile
from .workflow1 import _fit_from_row, build_application, store_application

log = logging.getLogger("jobbit.tailor_one")


def run(job_id: str) -> str:
    cfg, profile = settings(), parse_profile()
    if llm.is_stubbed():
        raise SystemExit(f"No API key for provider {llm.provider()!r} — cannot tailor.")

    job = db.get_job(job_id)
    if not job:
        raise SystemExit(f"job {job_id} not found")
    if db.has_application(job_id):
        log.info("job already has tailored documents; nothing to do")
        db.set_tailor_requested(job_id, False)
        return "exists"
    if location_rule(job) == "restricted":
        db.set_tailor_requested(job_id, False)
        db.discard(job_id, "location")
        return "restricted"

    try:
        row, files = build_application(job, profile, cfg, _fit_from_row(job))
        store_application(row, files)  # also clears tailor_requested
    except Exception as e:
        # Clear the flag so the row leaves "Tailoring queued…" and shows "Tailor this job" again to retry,
        # and tell you why (most often Gemini's daily quota).
        db.set_tailor_requested(job_id, False)
        reason = "Gemini quota is exhausted for today — try again tomorrow" if isinstance(e, llm.QuotaExhausted) \
            else f"{type(e).__name__}: {e}"
        log.error("tailoring failed for %s: %s", job_id, reason)
        notify.telegram(f"⚠️ Couldn't tailor\n{job.title} @ {job.company}\n\n{reason}")
        raise SystemExit(reason)

    log.info("tailored %s @ %s", job.title, job.company)
    notify.telegram(f"📄 Tailored on request\n{job.title} @ {job.company}\n{secrets().dashboard_url}/applications/{row['id']}")
    return "tailored"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--job", required=True, help="job UUID to tailor")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    print(run(args.job))


if __name__ == "__main__":
    main()
