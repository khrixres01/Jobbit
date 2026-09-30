"use client";

import Link from "next/link";
import type { ScoredJob } from "@/lib/types";
import { timeAgo } from "@/lib/data";
import { Score } from "./ui";

/** One row in the ranked browse view: score, the job, its direct apply link, and either
 *  download buttons (docs ready) or a "Tailor this job" button (not tailored yet). */
export default function JobRow({ job, flag, onTailor, onDownload, busy }: {
  job: ScoredJob;
  flag?: "best" | "least";
  onTailor: (jobId: string) => void;
  onDownload: (path: string | null) => void;
  busy?: boolean;
}) {
  const app = job.application;
  const hasDocs = !!(app?.tailored_resume_file_url || app?.cover_letter_file_url);

  return (
    <div className="row">
      <Score value={job.fit_score} />
      <div className="row-main">
        <span className="row-title">
          {job.title}
          {flag === "best" && <span className="fit-flag fit-best">Best fit</span>}
          {flag === "least" && <span className="fit-flag fit-least">Least fit</span>}
        </span>
        <span className="row-meta">
          {job.company} · {job.location_text || "Remote"} · {job.source}
          {job.location_eligibility === "visa_sponsorship" && <> · visa sponsorship</>}
          {job.posted_date && <> · posted {timeAgo(job.posted_date)}</>}
        </span>
        {job.fit_rationale && <span className="row-detail">{job.fit_rationale}</span>}
      </div>
      <span className="row-actions">
        <a className="btn btn-sm btn-primary" href={job.url} target="_blank" rel="noopener noreferrer">Apply on site ↗</a>
        {hasDocs ? (
          <>
            <button className="btn btn-sm btn-ghost" disabled={busy} onClick={() => onDownload(app!.tailored_resume_file_url)}>Résumé ↓</button>
            <button className="btn btn-sm btn-ghost" disabled={busy} onClick={() => onDownload(app!.cover_letter_file_url)}>Cover ↓</button>
            <Link href={`/applications/${app!.id}`} className="btn btn-sm btn-ghost">Open</Link>
          </>
        ) : job.tailor_requested ? (
          <span className="muted small">Tailoring queued…</span>
        ) : (
          <button className="btn btn-sm" disabled={busy} onClick={() => onTailor(job.id)}>Tailor this job</button>
        )}
      </span>
    </div>
  );
}
