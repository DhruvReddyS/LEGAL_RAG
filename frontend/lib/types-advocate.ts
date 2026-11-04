import type { SourceEvidence } from "@/lib/types";

/** A retrieved passage or a pinned provision. One shape across every tool. */
export interface AdvocateSource extends SourceEvidence {
  source_url?: string | null;
  document_id?: string | null;
  court?: string | null;
  decision_year?: number | null;
  authority_check?: CheckRow[];
}

/** Every judgment-based result carries this. It is never optional on screen. */
export interface CoverageStatement {
  judgments_held: number | null;
  judgments_searched: number | null;
  by_court: Record<string, number>;
  statement: string;
  absence_note: string;
}

export interface CheckRow {
  citation: string;
  code?: string;
  section?: string;
  finding: string;
  successors: string[];
  advice: string;
  needs_attention: boolean;
}

export type BailRouteKey = "regular" | "anticipatory" | "default" | "undertrial";
export type RouteStatus =
  | "entitled_on_text" | "discretionary" | "barred_on_text" | "not_yet"
  | "needs_review" | "undetermined" | "not_applicable";

export interface BailDate {
  label: string;
  date: string;
  computed_from: string;
  provision: string;
  state: "passed" | "today" | "upcoming";
}

export interface BailRouteFinding {
  route: BailRouteKey;
  label: string;
  status: RouteStatus;
  headline: string;
  forum: string;
  dates: BailDate[];
  missing: string[];
  cautions: string[];
  sources: AdvocateSource[];
}

export interface PrecedentPassage {
  source: AdvocateSource;
  holding_language: string[];
}

export interface BailAssessment {
  as_of: string;
  routes: BailRouteFinding[];
  method: string;
  pre_bnss_notice: {
    text: string;
    sources: AdvocateSource[];
    counterparts: { route: string; repealed_provision: string; bnss_provision: string; elements_changed: boolean }[];
  } | null;
  authorities: PrecedentPassage[];
  authorities_note: string;
  coverage: CoverageStatement;
  work_product_id?: string;
}

export interface DraftField {
  name: string;
  label: string;
  required: boolean;
  long: boolean;
  kind: string;
  options: { value: string; label: string }[];
}

export interface DraftTemplateInfo {
  key: string;
  title: string;
  description: string;
  uses_grounds: boolean;
  fields: DraftField[];
}

export interface VerifiedClaim {
  text: string;
  citations: AdvocateSource[];
}

export interface DraftContent {
  draft_type: string;
  title: string;
  fields: Record<string, string>;
  facts: string;
  grounds: VerifiedClaim[];
  rejected_ground_count: number;
  authorities: AdvocateSource[];
  statutory_provisions: AdvocateSource[];
  authority_checks: CheckRow[];
  computed_limit: { label: string; date: string; provision: string; computed_from: string } | null;
  missing_fields: string[];
  notes: string[];
  rendered_text: string;
  disclaimer: string;
}

export interface WorkSummary {
  id: string;
  case_id: string;
  kind: string;
  version: number;
  status: string;
  title: string;
  created_at: string;
}

export interface WorkDetail<T = unknown> extends WorkSummary {
  content: T;
}

export interface BriefSection {
  key: string;
  title: string;
  claims: VerifiedClaim[];
}

export interface BriefContent {
  kind: "brief" | "synopsis";
  sections: BriefSection[];
  proposed_count: number;
  verified_count: number;
  rejected_count: number;
  note: string;
  partial_review: boolean;
  passages_read: number;
  passages_total: number;
  documents_read: number;
  provisions_in_record: CheckRow[];
  disclaimer: string;
}

export type EventState = "done" | "overdue" | "due_today" | "due_soon" | "upcoming";

export interface CalendarEvent {
  id: string;
  case_id: string;
  case_title?: string;
  kind: "hearing" | "limitation" | "filing" | "other";
  title: string;
  due_on: string;
  notes: string | null;
  basis: Record<string, unknown>;
  completed: boolean;
  state: EventState;
  days_from_today: number;
}

export interface LimitationArticle {
  key: string;
  article: string;
  description: string;
  division: string;
  period: string;
  runs_from: string;
  caution: string;
}

export interface LimitationResult {
  article: string;
  description: string;
  period: string;
  runs_from: string;
  excluded_days: number;
  last_day: string;
  steps: string[];
  not_applied: string[];
  caution: string;
  sources: AdvocateSource[];
  basis_label: string;
  event: CalendarEvent | null;
}

export interface HeldJudgmentSummary {
  document_id: string;
  title: string;
  court: string;
  decision_year: number | null;
  decision_date: string | null;
  source_url: string | null;
}

export interface JudgmentCatalogue {
  coverage: CoverageStatement;
  year_min: number | null;
  year_max: number | null;
  undated: number | null;
  judgments: HeldJudgmentSummary[];
}

export interface PrecedentGroup extends HeldJudgmentSummary {
  passages: PrecedentPassage[];
}

export interface PrecedentResult {
  coverage: CoverageStatement;
  scope_note: string;
  results: PrecedentGroup[];
  empty_note: string;
  method: string;
}

export interface HeldCandidate extends HeldJudgmentSummary {
  match_basis: string;
  confidence: "likely" | "possible";
  match_note: string;
}

export interface TreatmentResult {
  label: string;
  limits: string[];
  coverage: CoverageStatement;
  reference: string;
  recognised: boolean;
  held: HeldCandidate[];
  cited_by: (HeldJudgmentSummary & {
    passages: {
      window: string;
      words_near_reference: { word: string; cautionary: boolean }[];
      source: AdvocateSource;
    }[];
  })[];
  cites: string[];
  provisions: CheckRow[];
  cited_by_provision: (HeldJudgmentSummary & { pages: number[]; provision: string })[];
}

export interface OpponentCase {
  reference: string;
  proposition_context: string;
  held: boolean;
  candidates: HeldCandidate[];
  passages: AdvocateSource[];
  cited_in_held_judgments: number;
  not_found_note: string;
}

export interface OpponentResult {
  coverage: CoverageStatement;
  limits: string[];
  cases: OpponentCase[];
  provisions: CheckRow[];
  repealed_provisions: number;
  needs_attention: number;
  work_product_id?: string;
}

export interface ComparisonPoint {
  dimension: string;
  first: VerifiedClaim | null;
  second: VerifiedClaim | null;
}

export interface ComparisonContent {
  points: ComparisonPoint[];
  proposed_count: number;
  verified_count: number;
  note: string;
  second_is_user_account: boolean;
  first: HeldJudgmentSummary;
  second: HeldJudgmentSummary | null;
  second_title: string;
  coverage: CoverageStatement;
  limit_note: string;
}

export interface DebateTurn {
  round: number;
  side: "for" | "against";
  arguments: VerifiedClaim[];
  proposed_count: number;
  rejected_count: number;
  note: string;
}

export interface DebateContent {
  proposition: string;
  facts: string | null;
  rounds: number;
  turns: DebateTurn[];
  verified_count: number;
  proposed_count: number;
  rejected_count: number;
  repealed_authorities: { title: string; replaced_by: string | null }[];
  summary: string;
  disclaimer: string;
}

export type DebateStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export interface DebateRow {
  id: string;
  status: DebateStatus;
  progress: number;
  proposition: string;
  rounds: number;
  turns_total: number;
  turns_done: number;
  attempt_count: number;
  error_message: string | null;
  work_product_id: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface DebateProgress extends DebateRow {
  stage_label: string | null;
  debate: DebateContent | null;
}
