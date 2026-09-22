"""Job source adapters. Each fetch_* function returns list[Job] and never raises on a single bad board."""
from __future__ import annotations

import logging

from ..config import companies
from . import ashby, greenhouse, himalayas, lever, remoteok, remotive, weworkremotely, workable
from .base import client

log = logging.getLogger(__name__)


def fetch_all() -> tuple[list, dict]:
    cfg = companies()
    jobs, stats = [], {}
    with client() as http:
        tasks = [
            ("greenhouse", lambda: greenhouse.fetch(http, cfg.get("greenhouse", []))),
            ("lever", lambda: lever.fetch(http, cfg.get("lever", []))),
            ("ashby", lambda: ashby.fetch(http, cfg.get("ashby", []))),
            ("workable", lambda: workable.fetch(http, cfg.get("workable", []))),
            ("remotive", lambda: remotive.fetch(http, cfg.get("remotive", {}).get("categories", []))),
            ("remoteok", lambda: remoteok.fetch(http)),
            ("weworkremotely", lambda: weworkremotely.fetch(http, cfg.get("weworkremotely", {}).get("feeds", []))),
            ("himalayas", lambda: himalayas.fetch(http, cfg.get("himalayas", {}).get("pages", 3))),
        ]
        for name, task in tasks:
            try:
                found = task()
            except Exception:  # one broken source must not kill the run
                log.exception("source %s failed", name)
                found = []
            stats[name] = len(found)
            jobs.extend(found)
    return jobs, stats
