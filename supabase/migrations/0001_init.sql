-- Jobbit initial schema
-- Run in the Supabase SQL editor (or `supabase db push`) on a clean project.
-- The Python pipeline uses the service-role key (bypasses RLS).
-- The dashboard uses the anon key + a magic-link session; RLS restricts everything to the owner email.

-- ---------------------------------------------------------------------------
-- Types
-- ---------------------------------------------------------------------------
create type application_status as enum (
  'pending_review',
  'queued',
  'submitted',
  'needs_manual_action',
  'applied_manually',
  'skipped'
);

create type location_eligibility as enum (
  'worldwide',        -- open to anywhere
  'includes_nigeria', -- explicitly includes Africa / EMEA / Nigeria
  'restricted',       -- limited to regions that exclude Nigeria
  'unknown'
);

-- ---------------------------------------------------------------------------
-- Owner / settings (single-user app)
-- ---------------------------------------------------------------------------
create table app_settings (
  id           boolean primary key default true check (id), -- enforces a single row
  owner_email  text not null,
  updated_at   timestamptz not null default now()
);

-- Replace with your login email before running, or update afterwards.
insert into app_settings (owner_email) values ('abelhero116@gmail.com');

create or replace function is_owner() returns boolean
language sql stable security definer set search_path = public as $$
  select coalesce(
    (select lower(owner_email) from app_settings) = lower(auth.jwt() ->> 'email'),
    false
  );
$$;

-- ---------------------------------------------------------------------------
-- Profile (parsed from profile/master_profile.md; markdown stays the source of truth)
-- ---------------------------------------------------------------------------
create table profile (
  id            boolean primary key default true check (id), -- single row
  source_hash   text not null,          -- sha256 of master_profile.md, used to detect changes
  raw_markdown  text not null,
  contact       jsonb not null,
  skills        jsonb not null,         -- {category: [skill, ...]}
  certifications jsonb not null,        -- [{name, issuer, date}]
  education     jsonb not null,
  experiences   jsonb not null,         -- [{key, title, company, location, dates, bullets[], keywords}]
  advanced_context jsonb not null,      -- [bullet, ...]
  achievements  jsonb not null,         -- [bullet, ...]
  summary_rules text not null,
  tailoring_guidance text not null,
  parsed_at     timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Jobs: every ingested posting, including discarded ones (so they're never re-scored)
-- ---------------------------------------------------------------------------
create table jobs (
  id              uuid primary key default gen_random_uuid(),
  source          text not null,            -- greenhouse | lever | ashby | remotive | remoteok | weworkremotely | himalayas
  external_id     text not null,            -- id within the source
  dedupe_key      text not null,            -- normalized company|title, catches cross-posted jobs
  title           text not null,
  company         text not null,
  location_text   text,
  jd_text         text not null,
  url             text not null,            -- application URL
  posted_date     timestamptz,
  remote          boolean not null default false,
  location_eligibility location_eligibility not null default 'unknown',
  fit_score       smallint check (fit_score between 0 and 100),
  fit_rationale   text,
  scored_at       timestamptz,
  discard_reason  text,                     -- null = kept; otherwise stale | not_remote | no_url | keyword | location | below_threshold
  ingested_at     timestamptz not null default now(),
  unique (source, external_id)
);

create unique index jobs_dedupe_key_idx on jobs (dedupe_key);
create index jobs_ingested_at_idx on jobs (ingested_at desc);
create index jobs_scored_at_idx on jobs (scored_at desc) where scored_at is not null;

-- ---------------------------------------------------------------------------
-- Applications: one per job that cleared the fit threshold
-- ---------------------------------------------------------------------------
create table applications (
  id                         uuid primary key default gen_random_uuid(),
  job_id                     uuid not null unique references jobs(id) on delete cascade,
  fit_score                  smallint not null check (fit_score between 0 and 100),
  rationale                  text not null,
  generated_summary_text     text not null,  -- generated fresh for this job, never reused
  tailored_resume_text       text not null,  -- plain-text rendering of the tailored resume
  tailored_resume_json       jsonb,          -- structured version used to render files
  tailored_resume_file_url   text,           -- storage path of the PDF (private bucket; dashboard signs it)
  tailored_resume_docx_url   text,           -- storage path of the DOCX
  cover_letter_text          text not null,
  cover_letter_file_url      text,           -- storage path of the PDF
  cover_letter_docx_url      text,           -- storage path of the DOCX
  validation_warnings        jsonb not null default '[]'::jsonb, -- fabrication-guard findings shown on the dashboard
  status                     application_status not null default 'pending_review',
  status_detail              text,           -- e.g. why it needs manual action
  created_at                 timestamptz not null default now(),
  updated_at                 timestamptz not null default now()
);

create index applications_status_idx on applications (status, created_at desc);

create or replace function set_updated_at() returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger applications_updated_at
  before update on applications
  for each row execute function set_updated_at();

-- ---------------------------------------------------------------------------
-- Logs
-- ---------------------------------------------------------------------------
create table application_events (
  id              bigint generated always as identity primary key,
  application_id  uuid not null references applications(id) on delete cascade,
  event           text not null,          -- created | apply_requested | submitted | needs_manual_action | skipped | applied_manually
  detail          jsonb not null default '{}'::jsonb,
  created_at      timestamptz not null default now()
);

create index application_events_app_idx on application_events (application_id, created_at desc);

create table pipeline_runs (
  id           bigint generated always as identity primary key,
  workflow     text not null,             -- scrape | apply
  started_at   timestamptz not null default now(),
  finished_at  timestamptz,
  stats        jsonb not null default '{}'::jsonb,
  error        text
);

-- ---------------------------------------------------------------------------
-- Row level security: owner only. Service role bypasses RLS.
-- ---------------------------------------------------------------------------
alter table app_settings        enable row level security;
alter table profile             enable row level security;
alter table jobs                enable row level security;
alter table applications        enable row level security;
alter table application_events  enable row level security;
alter table pipeline_runs       enable row level security;

create policy owner_read on app_settings       for select using (is_owner());
create policy owner_read on profile            for select using (is_owner());
create policy owner_read on jobs               for select using (is_owner());
create policy owner_read on pipeline_runs      for select using (is_owner());
create policy owner_read on application_events for select using (is_owner());
create policy owner_read on applications       for select using (is_owner());

-- The dashboard may only change status (Skip / Mark as Applied Manually).
-- Moving to 'queued' happens in the Edge Function, which also fires Workflow 2.
create policy owner_update on applications for update
  using (is_owner())
  with check (is_owner() and status in ('skipped', 'applied_manually', 'pending_review'));

create policy owner_insert_event on application_events for insert with check (is_owner());

-- Column-level guard: authenticated users can only update status fields.
revoke update on applications from authenticated;
grant update (status, status_detail) on applications to authenticated;

-- ---------------------------------------------------------------------------
-- Storage: private bucket for generated documents
-- ---------------------------------------------------------------------------
insert into storage.buckets (id, name, public)
values ('documents', 'documents', false)
on conflict (id) do nothing;

create policy owner_read_documents on storage.objects for select
  using (bucket_id = 'documents' and is_owner());
