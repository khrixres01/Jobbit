# Jobbit

Assisted remote job search: scrape → filter → score → tailor → **you review the dashboard and apply yourself**.
The pipeline never submits applications. It surfaces every job scored **6+/10** and posted in the **last 2 weeks**,
ranked best fit first, each with its direct apply link. It auto-tailors a résumé + cover letter for the best-fit
picks; click "Tailor this job" on any other match to queue tailoring on the next run. You download the docs and apply.

```
profile/master_profile.md      single source of truth for all generated content
config/settings.yaml           thresholds, caps, models, title keywords
config/companies.yaml          Greenhouse / Lever / Ashby boards + feed settings
supabase/migrations/           schema (run 0001–0004 in order)
supabase/functions/            trigger-tailor Edge Function (on-demand "Tailor this job")
jobbit/                        Python pipeline
  sources/                     one adapter per job source
  filters.py                   recency (14d) / remote / URL / title / location rules
  scoring.py                   LLM fit score + location eligibility + JD focus
  tailoring.py                 fresh summary, tailored resume, cover letter
  validation.py                fabrication guard
  documents.py                 PDF + DOCX rendering
  workflow1.py                 pipeline entry point (scrape → tailor → store → notify)
  tailor_one.py                tailor a single job on demand (--job <uuid>)
dashboard/                     Next.js dashboard (browse, rank, download, apply yourself)
.github/workflows/scrape.yml   pipeline cron (every 4h)
.github/workflows/tailor.yml   per-job tailoring, fired by the dashboard button
```

## On-demand tailoring

Best-fit jobs (`tailoring.auto_tailor_top_n`) are tailored automatically each run. For anything else,
the dashboard's **Tailor this job** button calls the `trigger-tailor` Edge Function, which fires
`tailor.yml` for that one job; documents land in ~2-3 minutes. Setup: deploy the function and add a
GitHub PAT (see `supabase/functions/README.md`).

## Setup

1. **Supabase**: create the project, open SQL Editor, run the migrations in `supabase/migrations/` in order
   (`0001_init.sql`, `0002_screening.sql`, `0003_assist_only.sql`).
   Check the `owner_email` insert near the top is the email you'll log into the dashboard with.
2. **Telegram**: message @BotFather → `/newbot` → token. Send your bot a message, then open
   `https://api.telegram.org/bot<TOKEN>/getUpdates` to read your `chat.id`.
3. **GitHub**: repo → Settings → Secrets and variables → Actions:
   - Secrets: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
   - Variable: `DASHBOARD_URL`
4. Actions tab → "Workflow 1" → Run workflow (tick dry run first).

## Local

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # Windows path; bin/ on macOS/Linux
cp .env.example .env
python -m jobbit.workflow1 --dry-run --limit 5   # no DB writes; stubbed LLM if no key; docs in ./out
python -m jobbit.workflow1                       # real run
```

## How the no-fabrication rule is enforced

1. The prompt includes the full master profile and its rules; model output is structured (JSON schema).
2. Names, contact details, job titles, companies, dates, education, and cert names are rendered from the parsed
   profile, never from model text. Skills not verbatim in the profile are dropped.
3. `validation.py` flags numbers, known tools, and in-progress certs (GCP, Six Sigma) not supported by the profile.
   Flags trigger one regeneration; remaining flags are saved to `applications.validation_warnings` for review.

## Costs

| Piece | Cost |
|---|---|
| GitHub Actions | Free (private repo: 2,000 min/mo; a run takes ~5–10 min × 180 runs/mo, more when Gemini is overloaded, so keep an eye on it) |
| Supabase, Vercel, Telegram | Free tiers |
| Gemini API | Free tier (small per-model daily quotas; models fall back in order, see `settings.yaml`). Switch `llm.provider` to `anthropic` to use Claude (paid) |

Supabase free projects pause after 7 days with no API activity; the 4-hourly workflow prevents that.
