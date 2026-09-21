"use client";

import { useEffect, useState } from "react";
import { Card, Empty } from "@/components/ui";
import { fetchRuns, timeAgo, type Run } from "@/lib/data";

const REASONS: Record<string, string> = {
  kept: "kept", stale: "too old", keyword: "title", not_remote: "not remote", no_url: "no URL", location: "location",
};

function duration(r: Run) {
  if (!r.finished_at) return "—";
  const s = Math.round((new Date(r.finished_at).getTime() - new Date(r.started_at).getTime()) / 1000);
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
}

export default function RunsPage() {
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { fetchRuns(30).then(setRuns).catch((e) => setError(e.message)); }, []);

  if (error) return <div className="page"><p className="error">{error}</p></div>;
  if (!runs) return <div className="page"><p className="muted">Loading…</p></div>;

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Pipeline runs</h1>
          <p className="muted">Workflow 1 runs every 4 hours on GitHub Actions</p>
        </div>
      </header>
      <Card>
        {runs.length === 0 ? <Empty>No runs yet.</Empty> : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th>Started</th><th>Result</th><th className="num">New jobs</th><th>Filtered out</th>
                    <th>Scoring</th><th className="num">Drafted</th><th className="num">Took</th></tr>
              </thead>
              <tbody>
                {runs.map((r) => {
                  const s = r.stats || {};
                  const pre = Object.entries(s.prefilter || {}).filter(([k]) => k !== "kept")
                    .map(([k, v]) => `${v} ${REASONS[k] ?? k}`).join(", ");
                  const sc = Object.entries(s.scoring || {}).map(([k, v]) => `${v} ${k.replace(/_/g, " ")}`).join(", ");
                  return (
                    <tr key={r.id}>
                      <td title={new Date(r.started_at).toLocaleString()}>{timeAgo(r.started_at)}</td>
                      <td>
                        <span className={r.error ? "dot dot-bad" : r.finished_at ? "dot dot-ok" : "dot dot-run"} aria-hidden />
                        {r.error ? <span className="error" title={r.error}>Failed</span> : r.finished_at ? "Completed" : "Running"}
                      </td>
                      <td className="num">{s.new ?? "—"}</td>
                      <td className="muted small">{pre || "—"}</td>
                      <td className="muted small">{sc || "—"}</td>
                      <td className="num">{s.applications_created ?? "—"}</td>
                      <td className="num muted">{duration(r)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
