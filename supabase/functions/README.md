# Edge Functions

- `trigger-tailor`: powers the dashboard's **"Tailor this job"** button. Verifies the caller is the owner
  (their JWT email must match `app_settings.owner_email`), sets `jobs.tailor_requested = true`, and fires a
  per-job GitHub Actions run via `POST /repos/{owner}/{repo}/dispatches`. Documents land in ~2-3 minutes and
  the browse view polls until they appear. It only generates documents — it never submits anything.

## Deploy

```bash
supabase functions deploy trigger-tailor
supabase secrets set GH_TOKEN=<fine-grained PAT> GH_REPO=<owner/repo>
```

`GH_TOKEN` is a fine-grained GitHub PAT scoped to this repo with **Actions: read and write** (and Contents: read).
`SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are injected automatically. The matching GitHub Actions workflow
is `.github/workflows/tailor.yml`, which listens for the `tailor` `repository_dispatch` event.
