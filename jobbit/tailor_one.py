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
        return "exists"
    if location_rule(job) == "restricted":
        db.discard(job_id, "location")
        return "restricted"

    row, files = build_application(job, profile, cfg, _fit_from_row(job))
    store_application(row, files)  # also clears tailor_requested
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
