"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import AppRow from "@/components/AppRow";
import { Card, Empty } from "@/components/ui";
import { fetchApplications, setStatus } from "@/lib/data";
import { STATUS_LABEL, STATUS_ORDER, type Application, type Status } from "@/lib/types";

type Filter = "all" | Status;
type Sort = "newest" | "score";

export default function ApplicationsPage() {
  const [apps, setApps] = useState<Application[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [sort, setSort] = useState<Sort>("newest");
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() =>
    fetchApplications().then(setApps).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);

  const onStatus = async (id: string, s: Status) => {
    setBusy(true);
    try { await setStatus(id, s); await load(); } catch (e: any) { alert(e.message); }
    setBusy(false);
  };

  const shown = useMemo(() => {
    if (!apps) return [];
    const needle = q.trim().toLowerCase();
    return apps
      .filter((a) => filter === "all" || a.status === filter)
      .filter((a) => !needle || `${a.jobs.title} ${a.jobs.company} ${a.jobs.location_text ?? ""}`.toLowerCase().includes(needle))
      .sort((a, b) => sort === "score" ? b.fit_score - a.fit_score : b.created_at.localeCompare(a.created_at));
  }, [apps, filter, sort, q]);

  if (error) return <div className="page"><p className="error">{error}</p></div>;
  if (!apps) return <div className="page"><p className="muted">Loading…</p></div>;

  const count = (f: Filter) => (f === "all" ? apps.length : apps.filter((a) => a.status === f).length);

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Applications</h1>
          <p className="muted">{apps.length} drafted in total</p>
        </div>
      </header>

      <div className="toolbar">
        <div className="segmented" role="tablist">
          {(["all", ...STATUS_ORDER] as Filter[]).map((f) => (
            <button key={f} role="tab" aria-selected={filter === f}
                    className={filter === f ? "seg active" : "seg"} onClick={() => setFilter(f)}>
              {f === "all" ? "All" : STATUS_LABEL[f]} <span className="seg-count">{count(f)}</span>
            </button>
          ))}
        </div>
        <div className="toolbar-right">
          <input className="search" type="search" placeholder="Search title, company, location"
                 value={q} onChange={(e) => setQ(e.target.value)} />
          <select value={sort} onChange={(e) => setSort(e.target.value as Sort)} aria-label="Sort">
            <option value="newest">Newest first</option>
            <option value="score">Highest fit</option>
          </select>
        </div>
      </div>

      <Card>
        {shown.length === 0 ? (
          <Empty>{apps.length === 0 ? "No applications yet." : "Nothing matches this filter."}</Empty>
        ) : (
          <div className="rows">{shown.map((a) => <AppRow key={a.id} app={a} onStatus={onStatus} busy={busy} />)}</div>
        )}
      </Card>
    </div>
  );
}
