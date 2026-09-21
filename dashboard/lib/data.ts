"use client";

import { supabase } from "./supabase";
import type { Application, Status } from "./types";

export const LIST_COLUMNS =
  "id,fit_score,status,status_detail,created_at,updated_at,validation_warnings," +
  "jobs(title,company,source,location_text,location_eligibility,url,posted_date)";

export async function fetchApplications(): Promise<Application[]> {
  const { data, error } = await supabase()
    .from("applications").select(LIST_COLUMNS).order("created_at", { ascending: false });
  if (error) throw error;
  return data as unknown as Application[];
}

export type FunnelStage = { key: string; label: string; value: number; hint: string };

/** All-time pipeline funnel, from row counts (head requests: no rows transferred). */
export async function fetchFunnel(threshold = 70): Promise<FunnelStage[]> {
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
    { key: "passed", label: `Scored ${threshold}+`, value: passed, hint: "At or above your fit threshold" },
    { key: "apps", label: "Applications drafted", value: apps, hint: "Tailored resume + cover letter generated" },
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
