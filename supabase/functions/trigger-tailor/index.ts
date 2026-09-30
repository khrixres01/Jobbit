// trigger-tailor: dashboard "Tailor this job" -> flag the job and fire a per-job GitHub Actions run.
//
// The browser cannot hold a GitHub token, so this function does. It verifies the caller is the owner
// (their JWT email must match app_settings.owner_email), sets jobs.tailor_requested = true, and calls
// GitHub `POST /repos/{owner}/{repo}/dispatches` with a fine-grained PAT held as a function secret.
//
// Deploy:  supabase functions deploy trigger-tailor
// Secrets: supabase secrets set GH_TOKEN=<fine-grained PAT: Actions read/write on this repo> \
//                               GH_REPO=<owner/repo>
// (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are injected automatically.)

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { ...CORS, "Content-Type": "application/json" } });

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });

  try {
    const authHeader = req.headers.get("Authorization") ?? "";
    if (!authHeader.startsWith("Bearer ")) return json({ error: "Not signed in" }, 401);

    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
    const admin = createClient(supabaseUrl, serviceKey);

    // Identify the caller from their JWT and confirm they are the owner.
    const { data: userData, error: userErr } = await admin.auth.getUser(authHeader.replace("Bearer ", ""));
    if (userErr || !userData.user?.email) return json({ error: "Invalid session" }, 401);

    const { data: settings } = await admin.from("app_settings").select("owner_email").limit(1).single();
    if (!settings || settings.owner_email.toLowerCase() !== userData.user.email.toLowerCase()) {
      return json({ error: "Not authorized" }, 403);
    }

    const { job_id } = await req.json().catch(() => ({}));
    if (!job_id) return json({ error: "job_id is required" }, 400);

    // The job must exist, be a kept match, and not already have documents.
    const { data: job } = await admin
      .from("jobs")
      .select("id, discard_reason, applications(id)")
      .eq("id", job_id)
      .single();
    if (!job) return json({ error: "Job not found" }, 404);
    if (job.discard_reason) return json({ error: `Job was discarded (${job.discard_reason})` }, 409);
    if ((job.applications as unknown[])?.length) return json({ error: "Already tailored" }, 409);

    // Flag it (so the row shows "Tailoring queued…" immediately) and dispatch the run.
    await admin.from("jobs").update({ tailor_requested: true }).eq("id", job_id);

    const ghToken = Deno.env.get("GH_TOKEN")!;
    const ghRepo = Deno.env.get("GH_REPO")!; // "owner/repo"
    const resp = await fetch(`https://api.github.com/repos/${ghRepo}/dispatches`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${ghToken}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: JSON.stringify({ event_type: "tailor", client_payload: { job_id } }),
    });
    if (!resp.ok) {
      const detail = await resp.text();
      return json({ error: `GitHub dispatch failed (${resp.status}): ${detail}` }, 502);
    }

    return json({ ok: true, status: "queued" });
  } catch (e) {
    return json({ error: String(e) }, 500);
  }
});
