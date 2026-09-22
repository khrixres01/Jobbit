"""Workflow 2: submit one application, triggered by your Apply click.

    python -m jobbit.workflow2 --application <uuid>

Runs only for applications you queued via the dashboard. Anything it cannot complete safely
(CAPTCHA, login wall, unknown form, missing answer, any error) ends as needs_manual_action
with a Telegram alert — it never guesses and never bypasses a CAPTCHA.
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from . import db, notify
from .applier import ManualAction, Submitted, detect_ats, submit
from .config import ROOT, secrets

log = logging.getLogger("jobbit.workflow2")
ARTIFACTS = ROOT / "apply_artifacts"

DOC_FIELDS = {
    "resume_pdf": "tailored_resume_file_url",
    "resume_docx": "tailored_resume_docx_url",
    "cover_pdf": "cover_letter_file_url",
    "cover_docx": "cover_letter_docx_url",
}


def _link(app: dict) -> str:
    return f"{secrets().dashboard_url}/applications/{app['id']}"


def hand_back(app: dict, reason: str, detail: dict | None = None) -> None:
    job = app["jobs"]
    db.set_application_status(app["id"], "needs_manual_action", reason)
    db.add_event(app["id"], "needs_manual_action", {"reason": reason, **(detail or {})})
    notify.telegram(
        f"⚠️ Needs manual action\n{job['title']} @ {job['company']}\n\n{reason}\n\n"
        f"Apply here: {job['url']}\nReview: {_link(app)}"
    )
    log.warning("handed back: %s", reason)


def run(application_id: str, force: bool = False, no_submit: bool = False, headless: bool = True) -> str:
    app = db.get_application(application_id)
    if not app:
        raise SystemExit(f"application {application_id} not found")
    job = app["jobs"]
    log.info("applying: %s @ %s via %s", job["title"], job["company"], detect_ats(job["url"]))

    # Only run for something you queued. This is the last line of defence behind the Apply click.
    if app["status"] != "queued" and not force:
        raise SystemExit(f"application is '{app['status']}', not 'queued' — nothing was submitted")

    missing: list[str] = []
    try:
        missing = [a["question"] for a in app.get("screening_answers") or [] if not (a.get("answer") or "").strip()]
        files = {}
        for key, column in DOC_FIELDS.items():
            path = app.get(column)
            if not path:
                hand_back(app, f"Missing generated document ({key})")
                return "needs_manual_action"
            files[key] = db.download(path)

        ARTIFACTS.mkdir(exist_ok=True)
        result: Submitted = submit(app, files, ARTIFACTS, no_submit=no_submit, headless=headless)
    except ManualAction as e:
        hand_back(app, e.reason, {**e.detail, "unanswered": missing})
        return "needs_manual_action"
    except Exception as e:
        log.exception("submission failed")
        hand_back(app, f"Submission failed: {type(e).__name__}: {e}")
        return "needs_manual_action"

    db.set_application_status(app["id"], "submitted", result.detail)
    db.add_event(app["id"], "submitted", result.evidence)
    notify.telegram(f"✅ Submitted\n{job['title']} @ {job['company']}\n{_link(app)}")
    log.info("submitted")
    return "submitted"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--application", required=True)
    ap.add_argument("--force", action="store_true", help="run even if the application isn't queued (testing)")
    ap.add_argument("--no-submit", action="store_true", help="fill the form and screenshot it, but never click submit")
    ap.add_argument("--show", action="store_true", help="run with a visible browser window")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    print(run(args.application, args.force, args.no_submit, headless=not args.show))


if __name__ == "__main__":
    main()
