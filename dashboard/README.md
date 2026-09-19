# Dashboard (Next.js on Vercel), not built yet

Planned: magic-link login via Supabase Auth, list view grouped by status, detail view with signed URLs for the
private `documents` bucket, and Apply / Skip / Mark as Applied Manually buttons.
Apply calls the `trigger-apply` Edge Function (see `supabase/functions/`), which holds the GitHub token.
