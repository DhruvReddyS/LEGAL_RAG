import type { Lang } from "./citizen-law/law";

export type LocalisedText = Record<Lang, string>;

export type NoticeProvision = {
  id: string;
  label: string;
  act_name: string;
  quote: string;
  page: number | null;
  source_url: string | null;
};

export type NoticeExplanation = {
  notice_type: string;
  type_label: LocalisedText;
  abstained: boolean;
  what_this_is: LocalisedText;
  risk: LocalisedText;
  statutory_deadline: LocalisedText | null;
  provisions: NoticeProvision[];
  demands: string[];
  deadlines: { days: number; quote: string }[];
  dates: { raw: string; iso: string | null; context: string }[];
  amounts: string[];
  cited_provisions: {
    raw: string;
    code: string | null;
    section: string;
    status: "replaced" | "in_force_code" | "not_checked";
    replaced_on?: string | null;
    successors: string[];
    no_successor: boolean;
    ingredients_changed: boolean;
  }[];
  flags: LocalisedText[];
  plain: { summary: string; demands: { plain: string; quote: string }[]; language: Lang } | null;
  plain_status: "not_requested" | "ok" | "unavailable" | "rejected";
  disclaimer: LocalisedText;
};

export type DeadlineStatus = "done" | "overdue" | "due_today" | "due_soon" | "upcoming";

export type CitizenDeadline = {
  id: string;
  title: string;
  due_on: string;
  remind_days_before: number;
  notes: string | null;
  source: string;
  provision_label: string | null;
  completed_at: string | null;
  created_at: string;
  status: DeadlineStatus;
  days_left: number;
};

export type DeadlineInput = {
  title: string;
  due_on: string;
  remind_days_before?: number;
  notes?: string | null;
  source?: "manual" | "notice" | "router";
  provision_label?: string | null;
};

/** A tool asks to record a date; My matter opens with the form filled in. */
export type DeadlineDraft = Omit<DeadlineInput, "remind_days_before">;
