"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import AppRow from "@/components/AppRow";
import Funnel from "@/components/Funnel";
import { Card, Empty, StatTile } from "@/components/ui";
import { fetchApplications, fetchFunnel, fetchRuns, setStatus, timeAgo, type FunnelStage, type Run } from "@/lib/data";
import type { Application, Status } from "@/lib/types";

export default function Overview() {
  const [apps, setApps] = useState<Application[] | null>(null);
  const [funnel, setFunnel] = useState<FunnelStage[] | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [a, f, r] = await Promise.all([fetchApplications(), fetchFunnel(), fetchRuns()]);
      setApps(a); setFunnel(f); setRuns(r);
    } catch (e: any) { setError(e.message); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const onStatus = async (id: string, s: Status) => {
    setBusy(true);
    try { await setStatus(id, s); await load(); } catch (e: any) { alert(e.message); }
    setBusy(false);
  };

  if (error) return <div className="page"><p className="error">{error}</p></div>;
  if (!apps || !funnel) return <div className="page"><p className="muted">Loading…</p></div>;

  const by = (s: Status) => apps.filter((a) => a.status === s);
  const toReview = by("pending_review");
  const manual = by("needs_manual_action");
  const applied = apps.filter((a) => a.status === "submitted" || a.status === "applied_manually");
  const attention = [...manual, ...toReview];
  const avg = apps.length ? Math.round(apps.reduce((n, a) => n + a.fit_score, 0) / apps.length) : null;
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
        <StatTile label="To review" value={toReview.length} accent={toReview.length > 0}
                  sub={toReview.length ? "Tailored and waiting for you" : "All caught up"} />
        <StatTile label="Needs manual action" value={manual.length}
                  sub="Auto-submit was blocked" />
        <StatTile label="Applied" value={applied.length}
                  sub={`${by("submitted").length} auto · ${by("applied_manually").length} manual`} />
        <StatTile label="Average fit" value={avg ?? "—"} sub={`across ${apps.length} drafted`} />
      </div>

      <div className="grid-2">
        <Card title="Needs your attention"
              action={<Link href="/applications" className="btn-link small">All applications →</Link>}>
          {attention.length === 0 ? (
            <Empty>Nothing to review right now. You'll get a Telegram message when new applications are ready.</Empty>
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
