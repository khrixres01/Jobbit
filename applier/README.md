# Workflow 2: Playwright applier, not built yet

Triggered by `repository_dispatch` (event `apply`, payload `{application_id}`) from the `trigger-apply` Edge Function.
Per-ATS form fillers (Greenhouse, Lever, Ashby) → `submitted`; any CAPTCHA, login wall, unknown field or error →
`needs_manual_action` + Telegram alert. No CAPTCHA bypassing.
