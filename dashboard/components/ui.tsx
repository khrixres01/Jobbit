import type { ReactNode } from "react";
import { STATUS_LABEL, type Status } from "@/lib/types";

// Status = reserved status colors, always paired with an icon + label (never color alone).
const STATUS_TONE: Record<Status, { tone: string; icon: string }> = {
  pending_review: { tone: "info", icon: "●" },
  needs_manual_action: { tone: "serious", icon: "▲" },
  queued: { tone: "warning", icon: "◷" },
  submitted: { tone: "good", icon: "✓" },
  applied_manually: { tone: "good", icon: "✓" },
  skipped: { tone: "muted", icon: "–" },
};

export function StatusBadge({ status }: { status: Status }) {
  const t = STATUS_TONE[status];
  return (
    <span className={`status status-${t.tone}`}>
      <span className="status-icon" aria-hidden>{t.icon}</span>
      {STATUS_LABEL[status]}
    </span>
  );
}

export function Score({ value, size = "md" }: { value: number; size?: "md" | "lg" }) {
  const band = value >= 85 ? "high" : value >= 70 ? "mid" : "low";
  return (
    <span className={`score score-${size} score-${band}`} title={`Fit score ${value}/100`}>
      {value}
    </span>
  );
}

export function StatTile({ label, value, sub, accent }: { label: string; value: ReactNode; sub?: ReactNode; accent?: boolean }) {
  return (
    <div className={accent ? "tile tile-accent" : "tile"}>
      <div className="tile-label">{label}</div>
      <div className="tile-value">{value}</div>
      {sub && <div className="tile-sub">{sub}</div>}
    </div>
  );
}

export function Card({ title, action, children, className = "" }:
  { title?: ReactNode; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`card ${className}`}>
      {(title || action) && (
        <header className="card-head">
          <h2>{title}</h2>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="empty">{children}</p>;
}
