// Apply button backend. Verifies the caller is the owner, marks the application queued, and asks
// GitHub Actions to run Workflow 2. The GitHub token lives here as a function secret, never in the browser.
//
// Deploy:
//   supabase functions deploy trigger-apply
//   supabase secrets set GH_TOKEN=... GH_REPO=khrixres01/Jobbit
import { createClient } from "jsr:@supabase/supabase-js@2";

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { ...CORS, "Content-Type": "application/json" } });

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return json({ error: "POST only" }, 405);

  const url = Deno.env.get("SUPABASE_URL")!;
  const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
  const ghToken = Deno.env.get("GH_TOKEN");
  const ghRepo = Deno.env.get("GH_REPO");
  if (!ghToken || !ghRepo) return json({ error: "GH_TOKEN / GH_REPO not configured" }, 500);

  // 1. who is calling?
  const authHeader = req.headers.get("Authorization") ?? "";
  const caller = createClient(url, Deno.env.get("SUPABASE_ANON_KEY")!, {
    global: { headers: { Authorization: authHeader } },
  });
  const { data: userData, error: userErr } = await caller.auth.getUser();
  if (userErr || !userData.user) return json({ error: "not signed in" }, 401);

  const admin = createClient(url, serviceKey);
  const { data: settings } = await admin.from("app_settings").select("owner_email").single();
  if (!settings || settings.owner_email.toLowerCase() !== (userData.user.email ?? "").toLowerCase()) {
    return json({ error: "not the owner" }, 403);
  }

  // 2. the application must be one you're allowed to submit
  const { application_id } = await req.json().catch(() => ({}));
  if (!application_id) return json({ error: "application_id required" }, 400);

  const { data: app, error: appErr } = await admin
    .from("applications")
    .select("id, status, apply_attempts, jobs(title, company, url)")
    .eq("id", application_id)
    .single();
  if (appErr || !app) return json({ error: "application not found" }, 404);
  if (!["pending_review", "needs_manual_action"].includes(app.status)) {
    return json({ error: `application is ${app.status}; only pending_review or needs_manual_action can be applied` }, 409);
  }

  // 3. queue it, then ask GitHub to run Workflow 2
  await admin.from("applications").update({
    status: "queued",
    status_detail: "Submission queued — Workflow 2 is running",
    apply_attempts: (app.apply_attempts ?? 0) + 1,
    last_apply_at: new Date().toISOString(),
  }).eq("id", app.id);
  await admin.from("application_events").insert({
    application_id: app.id, event: "apply_requested", detail: { via: "dashboard" },
  });

  const gh = await fetch(`https://api.github.com/repos/${ghRepo}/dispatches`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${ghToken}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ event_type: "apply", client_payload: { application_id: app.id } }),
  });

  if (!gh.ok) {
    const detail = `Could not start Workflow 2 (GitHub ${gh.status})`;
    await admin.from("applications").update({ status: "needs_manual_action", status_detail: detail }).eq("id", app.id);
    await admin.from("application_events").insert({
      application_id: app.id, event: "needs_manual_action", detail: { reason: detail, body: await gh.text() },
    });
    return json({ error: detail }, 502);
  }

  return json({ ok: true, status: "queued" });
});
