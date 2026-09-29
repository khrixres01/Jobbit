# Dashboard (Next.js on Vercel)

Magic-link login via Supabase Auth. Assist-only: the dashboard never submits applications.

- **Matching jobs** (`/jobs`): every job scored 6+/10 and posted in the last 2 weeks, ranked best fit first,
  with the top and bottom flagged. Each row has a direct **Apply on site** link. Best-fit picks are tailored
  automatically; other rows show a **Tailor this job** button that flags the job for the next pipeline run.
- **Tailored docs** (`/applications`): jobs the pipeline has tailored, with signed-URL downloads (résumé + cover
  letter, PDF/DOCX) from the private `documents` bucket, plus Skip / Mark as applied manually.

You download the documents and apply yourself using the direct link.
