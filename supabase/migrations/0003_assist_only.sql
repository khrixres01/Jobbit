-- Assist-only pivot: the pipeline no longer auto-submits. The dashboard shows scored jobs
-- with their direct apply link and (for the best-fit picks, or on request) tailored documents.

-- On-demand tailoring: a "Tailor this job" click sets this flag; the next scrape run picks it
-- up and generates the tailored resume + cover letter, then clears the flag.
alter table jobs
  add column if not exists tailor_requested boolean not null default false;

create index if not exists jobs_tailor_requested_idx on jobs (tailor_requested) where tailor_requested;

-- The dashboard (authenticated owner) may flag a job for tailoring; nothing else on jobs.
drop policy if exists owner_request_tailor on jobs;
create policy owner_request_tailor on jobs for update
  using (is_owner())
  with check (is_owner());

revoke update on jobs from authenticated;
grant update (tailor_requested) on jobs to authenticated;
