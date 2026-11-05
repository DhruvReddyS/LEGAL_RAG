import { request } from "@/lib/api";
import { toQuery } from "@/lib/admin-presentation";

// ------------------------------------------------- notices on a person's account

export interface LawChangeNotice {
  id: string;
  document_title: string;
  previous_status: string;
  current_status: string;
  superseded_by: string | null;
  effective: string | null;
  basis: string | null;
  conversation_id: string;
  conversation_title: string;
  created_at: string;
  read_at: string | null;
}

export interface LawChangeNotices {
  unread: number;
  notices: LawChangeNotice[];
}

export const getLawChangeNotices = () => request<LawChangeNotices>("/account/law-changes");

export const markLawChangeRead = (id: string) =>
  request<void>(`/account/law-changes/${encodeURIComponent(id)}/read`, { method: "POST" });

export const markAllLawChangesRead = () =>
  request<{ marked_read: number }>("/account/law-changes/read-all", { method: "POST" });

// ---------------------------------------------------------------- amendment watch

const CONSOLE = "/admin/console";

export type FindingStatus = "open" | "reviewed" | "dismissed";

export interface AmendmentFinding {
  id: string;
  kind: string;
  title: string;
  detail: string;
  source?: string;
  first_seen: string;
  review_status: FindingStatus;
  review_note: string | null;
}

export interface WatchedAct {
  watch_id: string;
  title: string;
  reasons: string[];
  currency: string;
  superseded_by: string | null;
  standing: "checked" | "no_local_source";
  last_checked: string | null;
  source_url: string | null;
}

export interface AmendmentWatch {
  has_run: boolean;
  checked_at?: string;
  mode?: "offline" | "network";
  watched?: number;
  coverage?: { checked?: number; no_local_source?: number };
  source_entries?: number;
  findings: AmendmentFinding[];
  open_findings: number;
  watch: WatchedAct[];
  watch_total: number;
  page: number;
  page_size: number;
}

export const getAmendmentWatch = (page: number, pageSize: number) =>
  request<AmendmentWatch>(`${CONSOLE}/corpus/amendments${toQuery({ page, page_size: pageSize })}`);

export const reviewAmendmentFinding = (id: string, status: FindingStatus, note: string | null) =>
  request<{ id: string; review_status: FindingStatus; review_note: string | null }>(
    `${CONSOLE}/corpus/amendments/findings/${encodeURIComponent(id)}`,
    { method: "PUT", body: JSON.stringify({ status, note }) },
  );

// ------------------------------------------------------------------ expert review

export type ClaimVerdict = "correct" | "incorrect" | "unsure";

export interface ReviewMeasure {
  claim_accuracy: number | null;
  interval_95: [number, number] | null;
  sample_size: number;
  correct: number;
  incorrect: number;
  unsure: number;
  unreviewed: number;
  answers_reviewed: number;
}

export interface ReviewCitation {
  number: number | null;
  title: string | null;
  section: string | null;
  source_url: string | null;
  excerpt: string;
}

export interface ReviewClaim {
  id: string;
  text: string;
  verdict: ClaimVerdict | null;
  note: string | null;
}

export interface ReviewItem {
  id: string;
  answered_month: string;
  citations: ReviewCitation[];
  claims: ReviewClaim[];
}

export interface ReviewQueue {
  measure: ReviewMeasure;
  total: number;
  page: number;
  page_size: number;
  items: ReviewItem[];
}

export const getReviewQueue = (status: "open" | "done", page: number, pageSize: number) =>
  request<ReviewQueue>(`${CONSOLE}/quality/review${toQuery({ status, page, page_size: pageSize })}`);

export const sampleForReview = (count: number, days: number) =>
  request<{ requested: number; sampled: number; days: number }>(`${CONSOLE}/quality/review/sample`, {
    method: "POST",
    body: JSON.stringify({ count, days }),
  });

export const recordClaimVerdict = (id: string, verdict: ClaimVerdict | null, note: string | null) =>
  request<ReviewClaim>(`${CONSOLE}/quality/review/claims/${encodeURIComponent(id)}`, {
    method: "PUT",
    body: JSON.stringify({ verdict, note }),
  });
