-- Workflow 2, stage 1: screening answers drafted per application and editable by the owner.

alter table applications
  add column screening_answers jsonb not null default '[]'::jsonb,   -- [{key, question, answer, source, edited}]
  add column apply_attempts smallint not null default 0,
  add column last_apply_at timestamptz;

-- The dashboard may edit answers (and status). Everything else stays service-role only.
grant update (status, status_detail, screening_answers) on applications to authenticated;

-- Status values the dashboard itself may set. 'queued' is set by the trigger-apply Edge Function
-- (service role), never directly by the browser, so Apply still cannot bypass your click.
drop policy if exists owner_update on applications;
create policy owner_update on applications for update
  using (is_owner())
  with check (is_owner() and status in ('skipped', 'applied_manually', 'pending_review'));
