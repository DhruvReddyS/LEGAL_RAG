/** Shapes the administration console's API returns. */

export type GateStatus = "passed" | "failed" | "skipped" | "incomplete" | "not_run";

export interface GateResult {
  key: string;
  name: string;
  checks: string;
  status: GateStatus;
  excerpt: string;
}

export interface GateEvidence {
  label: string;
  gates: GateResult[];
  counts: Record<GateStatus, number>;
  all_passed: boolean;
  has_summary: boolean;
  updated_at: string | null;
  documents: string[];
}

export interface PlanStep {
  title: string;
  command: string;
  detail: string;
}

export interface ReleaseDecision {
  id: string;
  label: string;
  collection: string;
  decision: "approve" | "refuse";
  reason: string;
  override_failed_gates: boolean;
  gate_snapshot: { counts: Record<string, number>; gates: Record<string, GateStatus> };
  decided_by: string | null;
  decided_at: string;
}

export interface GateRun {
  id: string;
  label: string;
  collection: string;
  status: "queued" | "running" | "passed" | "failed" | "cancelled";
  exit_code: number | null;
  requested_at: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface ReleaseState {
  serving_collection: string;
  collections: {
    reachable: boolean;
    error_type?: string;
    collections: { name: string; points: number | null; status: string }[];
  };
  evidence: GateEvidence[];
  decisions: ReleaseDecision[];
  gate_runs: GateRun[];
  queue_blockers: string[];
  runner_command: string;
  rollback: { collection: string; steps: PlanStep[] } | null;
  live_switch_supported: boolean;
}

export interface CutoverPlan {
  collection: string;
  from_collection: string;
  steps: PlanStep[];
  rollback_steps: PlanStep[];
  live_switch_supported: boolean;
}

export type WorkQueue = "ocr" | "verification" | "currency";
export type WorkStatus = "open" | "in_progress" | "done";
export type CurrencyFlag = "current" | "unverified" | "warned" | "repealed_or_superseded";

export interface CorpusDocument {
  canonical_document_id: string;
  title: string;
  source_type: string;
  category: string;
  domain: string;
  jurisdiction: string | null;
  act_name: string | null;
  court: string | null;
  current_status: string;
  currency_flag: CurrencyFlag;
  currency_note: string | null;
  superseded_by: string | null;
  verified_official: boolean;
  quality_status: string;
  ocr_required: boolean;
  page_count: number;
  source_url: string | null;
  queues: WorkQueue[];
  quarantined: boolean;
  work_status: WorkStatus;
  work_note: string | null;
}

export interface CorpusBrowse {
  total_documents: number;
  total_pages: number;
  total: number;
  page: number;
  page_size: number;
  quarantined: number;
  facets: {
    source_type: Record<string, number>;
    domain: Record<string, number>;
    currency: Record<string, number>;
    queue: Record<WorkQueue, number>;
  };
  documents: CorpusDocument[];
}

export interface LiveDay {
  day: string;
  answers: number;
  abstention_rate: number | null;
  citation_coverage: number | null;
  unsupported_claims: number | null;
  verified_answers: number;
  latency_p50_ms: number | null;
  latency_p95_ms: number | null;
  feedback_down: number;
  feedback_total: number;
}

export interface StoredAnswerPoint {
  id: string;
  at: string;
  collection: string | null;
  abstention_correct: number | null;
  ground_coverage: number | null;
  citation_coverage: number | null;
  currency_correct: number | null;
  unsupported_claims_total: number | null;
  latency_p50_s: number | null;
}

export interface StoredRetrievalPoint {
  id: string;
  at: string;
  collection: string | null;
  recall_at_5: number | null;
  citation_accuracy_at_5: number | null;
  abstention_accuracy: number | null;
  false_abstention_rate: number | null;
}

export interface QualityDashboard {
  stored: { answers: StoredAnswerPoint[]; retrieval: StoredRetrievalPoint[] };
  live: {
    days: number;
    series: LiveDay[];
    totals: Omit<LiveDay, "day">;
  };
}

export type TriageStatus = "open" | "investigating" | "resolved" | "dismissed";

export interface FeedbackItem {
  id: string;
  message_id: string;
  rating: "up" | "down";
  has_correction: boolean;
  status: TriageStatus;
  confidence_score: number | null;
  citation_count: number;
  answered_at: string;
  case_linked: boolean;
  role: string;
}

export interface FeedbackList {
  total: number;
  page: number;
  page_size: number;
  items: FeedbackItem[];
}

export interface TracedCitation {
  number: number | null;
  chunk_id: string;
  title: string | null;
  source_type: string | null;
  page_start: number | null;
  page_end: number | null;
  court: string | null;
  act_name: string | null;
  section: string | null;
  source_url: string | null;
  excerpt: string | null;
  retrieval_score: number | null;
  verification_status: string | null;
  current_status: string | null;
  replaced_by: string | null;
  canonical_document_id: string | null;
  corpus_tier: string | null;
  found_in_corpus: boolean;
  quarantined: boolean;
}

export interface FeedbackTrace {
  id: string;
  message_id: string;
  rating: "up" | "down";
  status: TriageStatus;
  note: string | null;
  confidence_score: number | null;
  answered_at: string;
  case_linked: boolean;
  corpus_checked: boolean;
  answer: string | null;
  correction: string | null;
  has_correction: boolean;
  citations: TracedCitation[];
  citations_withheld: number;
}

export interface QuarantinePreview {
  canonical_document_id: string;
  title: string | null;
  in_manifest: boolean;
  current_status: string | null;
  points_in_serving_collection: number | null;
  corpus_tier: string | null;
  serving_collection: string;
  already_quarantined: boolean;
}

export interface QuarantineRow {
  id: string;
  canonical_document_id: string;
  title: string | null;
  reason: string;
  feedback_id: string | null;
  quarantined_at: string | null;
  released_at: string | null;
  release_reason: string | null;
}

export interface ConsoleUser {
  id: string;
  name: string;
  email: string;
  role: "citizen" | "police" | "advocate" | "admin";
  is_active: boolean;
  created_at: string;
  case_count: number;
  last_login_at: string | null;
  sessions_valid_from: string | null;
  force_password_reset: boolean;
  /** A provisioned account that has not yet replaced its first password. Clearing a reset leaves this. */
  first_password_change_pending: boolean;
  mfa_required: boolean;
  suspended_reason: string | null;
  manageable: boolean;
}

export interface UserDirectory {
  total: number;
  page: number;
  page_size: number;
  by_role: Record<string, number>;
  users: ConsoleUser[];
}

export interface RetentionCategory {
  key: string;
  label: string;
  description: string;
  minimum_days: number;
  days: number | null;
}

export interface RetentionRun {
  id: string;
  kind: "dry_run" | "purge";
  dry_run_id: string | null;
  counts: Record<string, number>;
  requested_by: string | null;
  created_at: string;
}

export interface RetentionState {
  categories: RetentionCategory[];
  runs: RetentionRun[];
  dry_run_valid_minutes: number;
}

export interface RetentionDryRun {
  id: string;
  counts: Record<string, number>;
  cutoffs: Record<string, string>;
  policy: Record<string, number | null>;
  created_at: string;
  expires_at: string;
  confirmation: string;
}

export interface ModelConfiguration {
  generation: { model: string; concurrency: number; keep_alive: string; small_tier: boolean };
  serving_collection: string;
  prompts: { name: string; fingerprint: string; measured_in_latest_run: boolean | null }[];
  latest_run: string | null;
  change_steps: PlanStep[];
}

export interface EvaluationRun {
  id: string;
  kind: "answers" | "retrieval";
  generated_at: string | null;
  collection: string | null;
  golden_set: string | null;
  generation_model: string | null;
  embedding_model: string | null;
  prompt_versions: Record<string, string>;
  metrics: Record<string, number>;
  by_role: Record<string, Record<string, number>>;
}

export interface MetricComparison {
  metric: string;
  a: number | null;
  b: number | null;
  delta: number | null;
  better: "a" | "b" | null;
}

export interface RunComparison {
  a: EvaluationRun;
  b: EvaluationRun;
  metrics: MetricComparison[];
  prompts: { name: string; a: string | null; b: string | null; changed: boolean }[];
  warnings: string[];
}

export interface ConsoleAuditEvent {
  id: string;
  actor_name: string | null;
  actor_email: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  metadata: Record<string, unknown>;
  timestamp: string;
}

export interface ConsoleAudit {
  total: number;
  page: number;
  page_size: number;
  actions: string[];
  resource_types: string[];
  events: ConsoleAuditEvent[];
}

export interface AuditFilters {
  action?: string;
  actor?: string;
  resource_type?: string;
  resource_id?: string;
  since?: string;
  until?: string;
  page?: number;
  page_size?: number;
}

export interface DependencyHealth {
  status: "ready" | "unavailable";
  duration_ms: number;
  error_type?: string;
  [key: string]: unknown;
}

export interface SystemHealth {
  ready: boolean;
  report: {
    status: string;
    dependencies: Record<string, DependencyHealth>;
    inference: Record<string, string>;
  };
  environment: string;
  serving_collection: string;
  schema_revision: string | null;
  job_worker_enabled: boolean;
  quarantined_documents: number;
  jobs: {
    by_status: Record<string, number>;
    oldest_queued_at: string | null;
    recent: {
      id: string;
      type: string;
      status: string;
      progress: number;
      attempts: number;
      error_code: string | null;
      created_at: string;
    }[];
  };
}
