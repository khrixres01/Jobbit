-- Assist-only cleanup: the app never fills forms, so the screening/auto-apply columns are dead.
-- Dropping a column also drops any column-level grants on it (from 0002_screening.sql).

alter table applications
  drop column if exists screening_answers,
  drop column if exists apply_attempts,
  drop column if exists last_apply_at;
