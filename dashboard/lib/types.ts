export type Status =
  | "pending_review"
  | "queued"
  | "submitted"
  | "needs_manual_action"
  | "applied_manually"
  | "skipped";

export const STATUS_ORDER: Status[] = [
  "pending_review",
  "needs_manual_action",
  "queued",
  "submitted",
  "applied_manually",
  "skipped",
];

export const STATUS_LABEL: Record<Status, string> = {
  pending_review: "Pending review",
  needs_manual_action: "Needs manual action",
  queued: "Queued",
  submitted: "Submitted",
  applied_manually: "Applied manually",
  skipped: "Skipped",
};

export type Job = {
  id: string;
  source: string;
  title: string;
  company: string;
  location_text: string | null;
  location_eligibility: string;
  jd_text: string;
  url: string;
  posted_date: string | null;
};

export type Application = {
  id: string;
  job_id: string;
  fit_score: number;
  rationale: string;
  generated_summary_text: string;
  tailored_resume_text: string;
  tailored_resume_file_url: string | null;
  tailored_resume_docx_url: string | null;
  cover_letter_text: string;
  cover_letter_file_url: string | null;
  cover_letter_docx_url: string | null;
  validation_warnings: string[];
  status: Status;
  status_detail: string | null;
  created_at: string;
  updated_at: string;
  jobs: Job;
};

export type AppEvent = { id: number; event: string; detail: Record<string, unknown>; created_at: string };
