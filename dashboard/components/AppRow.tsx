"use client";

import Link from "next/link";
import type { Application, Status } from "@/lib/types";
import { timeAgo } from "@/lib/data";
import { Score, StatusBadge } from "./ui";

export default function AppRow({ app, onStatus, busy }:
  { app: Application; onStatus?: (id: string, s: Status) => void; busy?: boolean }) {
  const j = app.jobs;
  const actionable = app.status === "pending_review" || app.status === "needs_manual_action";
  return (
    <div className="row">
      <Score value={app.fit_score} />
      <Link href={`/applications/${app.id}`} className="row-main">
        <span className="row-title">{j.title}</span>
        <span className="row-meta">
          {j.company} · {j.location_text || "Remote"} · {j.source}
          {app.validation_warnings.length > 0 && (
            <span className="warn-chip" title="Fabrication-guard warnings — review before sending">
              ⚠ {app.validation_warnings.length}
            </span>
          )}
        </span>
        {app.status_detail && <span className="row-detail">{app.status_detail}</span>}
      </Link>
      <StatusBadge status={app.status} />
      <span className="row-time muted small" title={new Date(app.created_at).toLocaleString()}>
        {timeAgo(app.created_at)}
      </span>
      <span className="row-actions">
        <Link href={`/applications/${app.id}`} className="btn btn-sm">Review</Link>
        {actionable && onStatus && (
          <button className="btn btn-sm btn-ghost" disabled={busy} onClick={() => onStatus(app.id, "skipped")}>Skip</button>
        )}
      </span>
    </div>
  );
}
