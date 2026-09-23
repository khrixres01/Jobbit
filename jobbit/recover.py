"""Hand a stuck application back to you.

Used by Workflow 2's failure step, and by Workflow 1 to rescue applications left 'queued'
when a run died before it could report anything.
"""
from __future__ import annotations

import argparse
import logging
from datetime import datetime, timedelta, timezone

from . import db, notify
from .config import secrets

log = logging.getLogger("jobbit.recover")
STUCK_AFTER = timedelta(minutes=45)


def hand_back(application_id: str, reason: str) -> None:
    app = db.get_application(application_id)
    if not app or app["status"] != "queued":
        log.info("nothing to recover for %s", application_id)
        return
    job = app["jobs"]
    db.set_application_status(application_id, "needs_manual_action", reason)
    db.add_event(application_id, "needs_manual_action", {"reason": reason, "recovered": True})
    notify.telegram(f"⚠️ Needs manual action\n{job['title']} @ {job['company']}\n\n{reason}\n\n"
                    f"Apply here: {job['url']}\nReview: {secrets().dashboard_url}/applications/{application_id}")
    log.warning("handed back %s: %s", application_id, reason)


def sweep_stuck() -> int:
    """Rescue anything left 'queued' longer than STUCK_AFTER."""
    cutoff = (datetime.now(timezone.utc) - STUCK_AFTER).isoformat()
    rows = (db.sb().table("applications").select("id,last_apply_at")
            .eq("status", "queued").lt("last_apply_at", cutoff).execute().data)
    for row in rows:
        hand_back(row["id"], "Submission never reported back (the run died or timed out)")
    return len(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--application")
    ap.add_argument("--reason", default="Workflow 2 failed before submitting")
    ap.add_argument("--sweep", action="store_true", help="recover every application stuck in 'queued'")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if args.sweep:
        print("recovered:", sweep_stuck())
    elif args.application:
        hand_back(args.application, args.reason)
    else:
        ap.error("pass --application or --sweep")


if __name__ == "__main__":
    main()
