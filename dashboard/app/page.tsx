"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import AppRow from "@/components/AppRow";
import Funnel from "@/components/Funnel";
import { Card, Empty, StatTile } from "@/components/ui";
import { fetchApplications, fetchFunnel, fetchRuns, fetchScoredJobs, setStatus, timeAgo, type FunnelStage, type Run } from "@/lib/data";
import type { Application, ScoredJob, Status } from "@/lib/types";

export default function Overview() {
  const [apps, setApps] = useState<Application[] | null>(null);
  const [scored, setScored] = useState<ScoredJob[] | null>(null);
  const [funnel, setFunnel] = useState<FunnelStage[] | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [a, j, f, r] = await Promise.all([fetchApplications(), fetchScoredJobs(), fetchFunnel(), fetchRuns()]);
      setApps(a); setScored(j); setFunnel(f); setRuns(r);
    } catch (e: any) { setError(e.message); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const onStatus = async (id: string, s: Status) => {
    setBusy(true);
    try { await setStatus(id, s); await load(); } catch (e: any) { alert(e.message); }
    setBusy(false);
  };

  if (error) return <div className="page"><p className="error">{error}</p></div>;
  if (!apps || !scored || !funnel) return <div className="page"><p className="muted">Loading…</p></div>;

  const by = (s: Status) => apps.filter((a) => a.status === s);
  const toReview = by("pending_review");
  const applied = by("applied_manually");
  const attention = toReview;
  const avg = scored.length ? Math.round(scored.reduce((n, j) => n + j.fit_score, 0) / scored.length) / 10 : null;
  const best = scored[0];
  const least = scored[scored.length - 1];
  const last = runs[0];

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Overview</h1>
          <p className="muted">
            {last ? <>Last pipeline run {timeAgo(last.started_at)}
              {last.error ? <span className="error"> · failed</span> : last.finished_at ? " · completed" : " · running"}</>
              : "The pipeline hasn't run yet."}
            {" · "}runs every 4 hours
          </p>
        </div>
      </header>

      <div className="tiles">
        <StatTile label="Matching jobs" value={scored.length} accent={scored.length > 0}
                  sub="Scored 6+/10, last 2 weeks" />
        <StatTile label="Docs to review" value={toReview.length}
                  sub={toReview.length ? "Tailored and waiting" : "All caught up"} />
        <StatTile label="Applied manually" value={applied.length}
                  sub="You marked these done" />
        <StatTile label="Average fit" value={avg ?? "—"} sub={`across ${scored.length} matches`} />
      </div>

      {scored.length > 0 && (
        <div className="tiles">
          <StatTile label="Best fit right now" accent
                    value={`${(best.fit_score / 10).toFixed(1)}/10`}
                    sub={`${best.title} · ${best.company}`} />
          <StatTile label="Least fit shown"
                    value={`${(least.fit_score / 10).toFixed(1)}/10`}
                    sub={`${least.title} · ${least.company}`} />
        </div>
      )}

      <div className="grid-2">
        <Card title="Tailored docs to review"
              action={<Link href="/jobs" className="btn-link small">Browse all matches →</Link>}>
          {attention.length === 0 ? (
            <Empty>No tailored docs waiting. Best-fit jobs are tailored automatically; click “Tailor this job” on any match to queue more.</Empty>
          ) : (
            <div className="rows">{attention.slice(0, 8).map((a) =>
              <AppRow key={a.id} app={a} onStatus={onStatus} busy={busy} />)}</div>
          )}
        </Card>

        <div className="stack">
          <Card title="Pipeline funnel" action={<span className="muted small">all time</span>}>
            <Funnel stages={funnel} />
          </Card>
          <Card title="Recent runs" action={<Link href="/runs" className="btn-link small">History →</Link>}>
            {runs.length === 0 ? <Empty>No runs yet.</Empty> : (
              <ul className="runs-mini">
                {runs.slice(0, 4).map((r) => (
                  <li key={r.id}>
                    <span className={r.error ? "dot dot-bad" : r.finished_at ? "dot dot-ok" : "dot dot-run"} aria-hidden />
                    <span>{timeAgo(r.started_at)}</span>
                    <span className="muted small">
                      {r.error ? "failed" : r.finished_at
                        ? `${r.stats?.new ?? 0} new · ${r.stats?.applications_created ?? 0} drafted`
                        : "running…"}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
