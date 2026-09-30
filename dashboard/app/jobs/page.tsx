"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import JobRow from "@/components/JobRow";
import { Card, Empty } from "@/components/ui";
import { BUCKET, supabase } from "@/lib/supabase";
import { fetchScoredJobs, requestTailor, MAX_AGE_DAYS } from "@/lib/data";
import type { ScoredJob } from "@/lib/types";

type Filter = "all" | "tailored" | "untailored";

async function download(path: string | null) {
  if (!path) return;
  const name = path.split("/").pop();
  const { data, error } = await supabase().storage.from(BUCKET).createSignedUrl(path, 300, { download: name });
  if (error) return alert(error.message);
  window.open(data.signedUrl, "_blank", "noopener");
}

export default function JobsPage() {
  const [jobs, setJobs] = useState<ScoredJob[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() =>
    fetchScoredJobs().then(setJobs).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);

  const hasDocs = (j: ScoredJob) =>
    !!(j.application?.tailored_resume_file_url || j.application?.cover_letter_file_url);

  // While any job is being tailored (flagged but no docs yet), poll so the download buttons
  // appear on their own when the GitHub Actions run finishes (~2-3 min).
  const pending = !!jobs?.some((j) => j.tailor_requested && !hasDocs(j));
  useEffect(() => {
    if (!pending) return;
    const t = setInterval(load, 15_000);
    return () => clearInterval(t);
  }, [pending, load]);

  const onTailor = async (jobId: string) => {
    setBusy(true);
    try { await requestTailor(jobId); await load(); } catch (e: any) { alert(e.message); }
    setBusy(false);
  };

  const shown = useMemo(() => {
    if (!jobs) return [];
    const needle = q.trim().toLowerCase();
    return jobs
      .filter((j) => filter === "all" || (filter === "tailored" ? hasDocs(j) : !hasDocs(j)))
      .filter((j) => !needle || `${j.title} ${j.company} ${j.location_text ?? ""}`.toLowerCase().includes(needle));
  }, [jobs, filter, q]);

  if (error) return <div className="page"><p className="error">{error}</p></div>;
  if (!jobs) return <div className="page"><p className="muted">Loading…</p></div>;

  // Best/least fit are relative to the whole ranked set (not the current search), so the labels stay meaningful.
  const bestId = jobs[0]?.id;
  const leastId = jobs[jobs.length - 1]?.id;

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Matching jobs</h1>
          <p className="muted">
            {jobs.length} scored 6+/10 · posted in the last {MAX_AGE_DAYS} days · best fit first — you apply yourself
          </p>
        </div>
      </header>

      <div className="toolbar">
        <div className="segmented" role="tablist">
          {(["all", "tailored", "untailored"] as Filter[]).map((f) => (
            <button key={f} role="tab" aria-selected={filter === f}
                    className={filter === f ? "seg active" : "seg"} onClick={() => setFilter(f)}>
              {f === "all" ? "All" : f === "tailored" ? "Docs ready" : "Not tailored"}
            </button>
          ))}
        </div>
        <div className="toolbar-right">
          <input className="search" type="search" placeholder="Search title, company, location"
                 value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
      </div>

      <Card>
        {shown.length === 0 ? (
          <Empty>{jobs.length === 0 ? "No matching jobs yet — the next pipeline run will fill this in." : "Nothing matches this filter."}</Empty>
        ) : (
          <div className="rows">
            {shown.map((j) => (
              <JobRow key={j.id} job={j}
                      flag={j.id === bestId ? "best" : j.id === leastId ? "least" : undefined}
                      onTailor={onTailor} onDownload={download} busy={busy} />
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
