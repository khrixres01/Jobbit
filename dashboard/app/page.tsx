"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { supabase } from "@/lib/supabase";
import { STATUS_LABEL, STATUS_ORDER, type Application, type Status } from "@/lib/types";

const COLLAPSED_BY_DEFAULT: Status[] = ["skipped", "applied_manually", "submitted"];

export default function ListPage() {
  const [apps, setApps] = useState<Application[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<Record<string, boolean>>({});

  useEffect(() => {
    supabase()
      .from("applications")
      .select("id,fit_score,status,status_detail,created_at,validation_warnings,jobs(title,company,source,location_text,location_eligibility)")
      .order("created_at", { ascending: false })
      .then(({ data, error }) => {
        if (error) setError(error.message);
        else setApps(data as unknown as Application[]);
      });
  }, []);

  if (error) return <main className="pad"><p className="error">{error}</p></main>;
  if (!apps) return <main className="pad"><p className="muted">Loading…</p></main>;

  return (
    <main className="pad">
      {apps.length === 0 && (
        <p className="muted">No applications yet. The pipeline runs every 4 hours and pings Telegram when there are new ones.</p>
      )}
      {STATUS_ORDER.map((status) => {
        const group = apps.filter((a) => a.status === status);
        if (group.length === 0) return null;
        const isOpen = open[status] ?? !COLLAPSED_BY_DEFAULT.includes(status);
        return (
          <section key={status} className="group">
            <h2 onClick={() => setOpen({ ...open, [status]: !isOpen })}>
              <span className={`badge ${status}`}>{STATUS_LABEL[status]}</span>
              <span className="muted">{group.length}</span>
              <span className="muted chevron">{isOpen ? "▾" : "▸"}</span>
            </h2>
            {isOpen && (
              <ul className="cards">
                {group.map((a) => (
                  <li key={a.id}>
                    <Link href={`/applications/${a.id}`} className="card">
                      <span className="score">{a.fit_score}</span>
                      <span className="grow">
                        <b>{a.jobs.title}</b>
                        <span className="muted"> · {a.jobs.company} · {a.jobs.location_text || "Remote"}</span>
                        {a.status_detail && <span className="detail">{a.status_detail}</span>}
                      </span>
                      {a.validation_warnings.length > 0 && (
                        <span className="warn" title="Fabrication-guard warnings">⚠ {a.validation_warnings.length}</span>
                      )}
                      <span className="muted small">{new Date(a.created_at).toLocaleDateString()}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>
        );
      })}
    </main>
  );
}
