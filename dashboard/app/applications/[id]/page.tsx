"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { BUCKET, supabase } from "@/lib/supabase";
import { setStatus, timeAgo } from "@/lib/data";
import { Score, StatusBadge } from "@/components/ui";
import type { AppEvent, Application, Status } from "@/lib/types";

type Tab = "resume" | "cover" | "jd";

async function openFile(path: string | null, download: boolean) {
  if (!path) return;
  const name = path.split("/").pop();
  const { data, error } = await supabase().storage.from(BUCKET)
    .createSignedUrl(path, 300, download ? { download: name } : undefined);
  if (error) return alert(error.message);
  window.open(data.signedUrl, "_blank", "noopener");
}

export default function DetailPage() {
  const { id } = useParams<{ id: string }>();
  const [app, setApp] = useState<Application | null>(null);
  const [events, setEvents] = useState<AppEvent[]>([]);
  const [tab, setTab] = useState<Tab>("resume");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const sb = supabase();
    const [a, e] = await Promise.all([
      sb.from("applications").select("*, jobs(*)").eq("id", id).single(),
      sb.from("application_events").select("*").eq("application_id", id).order("created_at", { ascending: false }),
    ]);
    if (a.error) setError(a.error.message);
    else setApp(a.data as unknown as Application);
    setEvents((e.data ?? []) as AppEvent[]);
  }, [id]);
  useEffect(() => { load(); }, [load]);

  const change = async (s: Status) => {
    setBusy(true);
    try { await setStatus(id, s); await load(); } catch (e: any) { alert(e.message); }
    setBusy(false);
  };

  if (error) return <div className="page"><p className="error">{error}</p></div>;
  if (!app) return <div className="page"><p className="muted">Loading…</p></div>;
  const job = app.jobs;
  const s = app.status;
  const actionable = s === "pending_review" || s === "needs_manual_action";
  const files = tab === "resume"
    ? { pdf: app.tailored_resume_file_url, docx: app.tailored_resume_docx_url }
    : tab === "cover" ? { pdf: app.cover_letter_file_url, docx: app.cover_letter_docx_url } : null;

  return (
    <div className="page">
      <Link href="/applications" className="btn-link small">← Applications</Link>

      <header className="detail-head">
        <Score value={app.fit_score} size="lg" />
        <div className="grow">
          <h1>{job.title}</h1>
          <p className="muted">
            {job.company} · {job.location_text || "Remote"} · via {job.source}
            {job.posted_date && <> · posted {new Date(job.posted_date).toLocaleDateString()}</>}
          </p>
        </div>
        <StatusBadge status={s} />
      </header>

      <div className="detail-grid">
        <div className="detail-main">
          {app.validation_warnings.length > 0 && (
            <div className="callout callout-warn">
              <b>⚠ Check before sending.</b> The fabrication guard flagged:
              <ul>{app.validation_warnings.map((w) => <li key={w}>{w}</li>)}</ul>
            </div>
          )}

          <section className="card">
            <div className="tabs">
              {([["resume", "Resume"], ["cover", "Cover letter"], ["jd", "Job description"]] as [Tab, string][]).map(([t, label]) => (
                <button key={t} className={tab === t ? "tab active" : "tab"} onClick={() => setTab(t)}>{label}</button>
              ))}
              <span className="grow" />
              {files && <>
                <button className="btn btn-sm btn-ghost" onClick={() => openFile(files.pdf, false)}>View PDF</button>
                <button className="btn btn-sm btn-ghost" onClick={() => openFile(files.pdf, true)}>PDF ↓</button>
                <button className="btn btn-sm btn-ghost" onClick={() => openFile(files.docx, true)}>DOCX ↓</button>
              </>}
            </div>
            <pre className="doc">
              {tab === "resume" ? app.tailored_resume_text : tab === "cover" ? app.cover_letter_text : job.jd_text}
            </pre>
          </section>
        </div>

        <aside className="detail-side">
          <section className="card">
            <h2 className="side-title">Actions</h2>
            <div className="action-stack">
              <a className="btn" href={job.url} target="_blank" rel="noopener noreferrer">Open job posting ↗</a>
              {actionable && (
                <button className="btn btn-primary" disabled title="Automated submission (Workflow 2) is not built yet">
                  Apply (coming soon)
                </button>
              )}
              {s !== "applied_manually" && s !== "submitted" && (
                <button className="btn" disabled={busy} onClick={() => change("applied_manually")}>Mark as applied manually</button>
              )}
              {actionable && <button className="btn btn-ghost" disabled={busy} onClick={() => change("skipped")}>Skip</button>}
              {(s === "skipped" || s === "applied_manually") && (
                <button className="btn btn-ghost" disabled={busy} onClick={() => change("pending_review")}>Move back to review</button>
              )}
            </div>
            {app.status_detail && <p className="muted small side-note">{app.status_detail}</p>}
          </section>

          <section className="card">
            <h2 className="side-title">Why it fits</h2>
            <p className="prose">{app.rationale}</p>
            <dl className="facts">
              <dt>Location</dt><dd className="cap">{job.location_eligibility.replace(/_/g, " ")}</dd>
              <dt>Drafted</dt><dd>{timeAgo(app.created_at)}</dd>
            </dl>
          </section>

          <section className="card">
            <h2 className="side-title">Summary written for this job</h2>
            <p className="prose">{app.generated_summary_text}</p>
          </section>

          {events.length > 0 && (
            <section className="card">
              <h2 className="side-title">History</h2>
              <ul className="timeline">
                {events.map((e) => (
                  <li key={e.id}>
                    <span className="cap">{e.event.replace(/_/g, " ")}</span>
                    <span className="muted small" title={new Date(e.created_at).toLocaleString()}>{timeAgo(e.created_at)}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </aside>
      </div>
    </div>
  );
}
