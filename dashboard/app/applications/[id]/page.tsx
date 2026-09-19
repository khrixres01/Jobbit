"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { BUCKET, supabase } from "@/lib/supabase";
import { STATUS_LABEL, type AppEvent, type Application, type Status } from "@/lib/types";

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

  const setStatus = async (status: Status, detail: string | null = null) => {
    setBusy(true);
    const sb = supabase();
    const { error } = await sb.from("applications").update({ status, status_detail: detail }).eq("id", id);
    if (!error) await sb.from("application_events").insert({ application_id: id, event: status, detail: { via: "dashboard" } });
    setBusy(false);
    if (error) alert(error.message);
    else load();
  };

  if (error) return <main className="pad"><p className="error">{error}</p></main>;
  if (!app) return <main className="pad"><p className="muted">Loading…</p></main>;
  const job = app.jobs;
  const s = app.status;

  return (
    <main className="pad detail-page">
      <Link href="/" className="muted">← All applications</Link>

      <div className="head">
        <div className="score big">{app.fit_score}</div>
        <div className="grow">
          <h1>{job.title}</h1>
          <p className="muted">
            {job.company} · {job.location_text || "Remote"} · eligibility: {job.location_eligibility} · via {job.source}
            {job.posted_date && <> · posted {new Date(job.posted_date).toLocaleDateString()}</>}
          </p>
          <p><span className={`badge ${s}`}>{STATUS_LABEL[s]}</span>
            {app.status_detail && <span className="muted"> {app.status_detail}</span>}</p>
        </div>
      </div>

      <div className="actions">
        <a className="button" href={job.url} target="_blank" rel="noopener noreferrer">Open job posting ↗</a>
        {(s === "pending_review" || s === "needs_manual_action") && (
          <button className="primary" disabled title="Automated submission (Workflow 2) is not built yet">Apply</button>
        )}
        {s !== "applied_manually" && s !== "submitted" && (
          <button disabled={busy} onClick={() => setStatus("applied_manually")}>Mark as applied manually</button>
        )}
        {(s === "pending_review" || s === "needs_manual_action") && (
          <button disabled={busy} onClick={() => setStatus("skipped")}>Skip</button>
        )}
        {(s === "skipped" || s === "applied_manually") && (
          <button disabled={busy} className="link" onClick={() => setStatus("pending_review")}>Move back to review</button>
        )}
      </div>

      {app.validation_warnings.length > 0 && (
        <div className="warnbox">
          <b>⚠ Check before sending.</b> The fabrication guard flagged:
          <ul>{app.validation_warnings.map((w) => <li key={w}>{w}</li>)}</ul>
        </div>
      )}

      <section className="panel">
        <h3>Fit rationale</h3>
        <p>{app.rationale}</p>
        <h3>Professional summary (generated for this job)</h3>
        <p>{app.generated_summary_text}</p>
      </section>

      <div className="tabs">
        {([["resume", "Resume"], ["cover", "Cover letter"], ["jd", "Job description"]] as [Tab, string][]).map(([t, label]) => (
          <button key={t} className={tab === t ? "tab active" : "tab"} onClick={() => setTab(t)}>{label}</button>
        ))}
        <span className="grow" />
        {tab === "resume" && <>
          <button className="link" onClick={() => openFile(app.tailored_resume_file_url, false)}>View PDF</button>
          <button className="link" onClick={() => openFile(app.tailored_resume_file_url, true)}>PDF ↓</button>
          <button className="link" onClick={() => openFile(app.tailored_resume_docx_url, true)}>DOCX ↓</button>
        </>}
        {tab === "cover" && <>
          <button className="link" onClick={() => openFile(app.cover_letter_file_url, false)}>View PDF</button>
          <button className="link" onClick={() => openFile(app.cover_letter_file_url, true)}>PDF ↓</button>
          <button className="link" onClick={() => openFile(app.cover_letter_docx_url, true)}>DOCX ↓</button>
        </>}
      </div>
      <pre className="doc">
        {tab === "resume" ? app.tailored_resume_text : tab === "cover" ? app.cover_letter_text : job.jd_text}
      </pre>

      {events.length > 0 && (
        <section className="panel">
          <h3>History</h3>
          <ul className="events">
            {events.map((e) => (
              <li key={e.id}><span className="muted">{new Date(e.created_at).toLocaleString()}</span> {e.event}</li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
