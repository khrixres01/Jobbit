"use client";

import { supabase } from "./supabase";
import type { Application, ScoredJob, Status } from "./types";

/** The fit threshold (0-100) at or above which jobs surface on the dashboard. Shown to you as x/10. */
export const THRESHOLD = 60;
/** Only advertise jobs posted within this many days. */
export const MAX_AGE_DAYS = 14;

export const LIST_COLUMNS =
  "id,fit_score,status,status_detail,created_at,updated_at,validation_warnings," +
  "jobs(title,company,source,location_text,location_eligibility,url,posted_date)";

export async function fetchApplications(): Promise<Application[]> {
  const { data, error } = await supabase()
    .from("applications").select(LIST_COLUMNS).order("created_at", { ascending: false });
  if (error) throw error;
  return data as unknown as Application[];
}

/** Ranked browse view: every job scored at/above the threshold and posted within the freshness window,
 *  best fit first, with its tailored documents (if the pipeline has generated them yet). */
export async function fetchScoredJobs(threshold = THRESHOLD): Promise<ScoredJob[]> {
  const cutoff = new Date(Date.now() - MAX_AGE_DAYS * 86400_000).toISOString();
  const { data, error } = await supabase()
    .from("jobs")
    .select(
      "id,source,title,company,location_text,location_eligibility,url,posted_date,fit_score,fit_rationale,scored_at,tailor_requested," +
      "application:applications(id,status,tailored_resume_file_url,tailored_resume_docx_url,cover_letter_file_url,cover_letter_docx_url)"
    )
    .is("discard_reason", null)
    .gte("fit_score", threshold)
    .not("scored_at", "is", null)
    .gte("posted_date", cutoff)
    .order("fit_score", { ascending: false });
  if (error) throw error;
  // Jobs you've applied to or skipped live on the Applications page, not here.
  const done = ["applied_manually", "skipped"];
  return (data as unknown as ScoredJob[]).filter((j) => !done.includes(j.application?.status ?? ""));
}

/** Ask the Edge Function to tailor this job now: it flags the job and fires a per-job GitHub Actions
 *  run. Documents appear in ~2-3 minutes; the browse view polls until they land. */
export async function requestTailor(jobId: string): Promise<void> {
  const { data, error } = await supabase().functions.invoke("trigger-tailor", { body: { job_id: jobId } });
  if (error) {
    // Edge Function errors carry the useful message in the response body.
    const body = await (error as any).context?.json?.().catch(() => null);
    throw new Error(body?.error ?? error.message);
  }
  if ((data as any)?.error) throw new Error((data as any).error);
}

export type FunnelStage = { key: string; label: string; value: number; hint: string };

/** All-time pipeline funnel, from row counts (head requests: no rows transferred). */
export async function fetchFunnel(threshold = THRESHOLD): Promise<FunnelStage[]> {
  const sb = supabase();
  const count = async (build: (q: any) => any) => {
    const { count, error } = await build(sb.from("jobs").select("id", { count: "exact", head: true }));
    if (error) throw error;
    return count ?? 0;
  };
  const [total, filteredOut, scored, passed, apps] = await Promise.all([
    count((q) => q),
    count((q) => q.in("discard_reason", ["stale", "keyword", "not_remote", "no_url"])),
    count((q) => q.not("scored_at", "is", null)),
    count((q) => q.gte("fit_score", threshold)),
    sb.from("applications").select("id", { count: "exact", head: true }).then((r) => r.count ?? 0),
  ]);
  return [
    { key: "ingested", label: "Jobs ingested", value: total, hint: "New postings from all 7 sources" },
    { key: "filtered", label: "Passed filters", value: total - filteredOut,
      hint: "Recent, explicitly remote, relevant title, has an apply URL" },
    { key: "scored", label: "Scored by AI", value: scored, hint: "Fit-scored against your master profile" },
    { key: "passed", label: `Scored ${threshold / 10}+/10`, value: passed, hint: "At or above your fit threshold — shown on the dashboard" },
    { key: "apps", label: "Tailored docs ready", value: apps, hint: "Resume + cover letter generated (best-fit picks + your requests)" },
  ];
}

export type Run = {
  id: number; workflow: string; started_at: string; finished_at: string | null;
  error: string | null; stats: Record<string, any>;
};

export async function fetchRuns(limit = 6): Promise<Run[]> {
  const { data, error } = await supabase()
    .from("pipeline_runs").select("*").order("id", { ascending: false }).limit(limit);
  if (error) throw error;
  return data as Run[];
}

export async function setStatus(id: string, status: Status, detail: string | null = null) {
  const sb = supabase();
  const { error } = await sb.from("applications").update({ status, status_detail: detail }).eq("id", id);
  if (error) throw error;
  await sb.from("application_events").insert({ application_id: id, event: status, detail: { via: "dashboard" } });
}

export function timeAgo(iso: string | null): string {
  if (!iso) return "—";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}
