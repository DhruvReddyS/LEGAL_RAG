/**
 * Whether the cited law still applies.
 *
 * "repealed" is distinct from "superseded": a superseded source cannot ground
 * a published claim at all, whereas a repealed Act still governs conduct from
 * before its repeal - an offence committed on 30 June 2024 is tried under the
 * Indian Penal Code - so it is cited with its successor named rather than
 * withheld.
 */
/**
 * Two distinct warnings, deliberately not merged.
 *
 * "no_longer_in_force" belongs to the repealed Act itself.
 * "concerns_repealed_provision" belongs to guidance, manuals and judgments
 * written against a provision that has since moved - documents which are
 * themselves still operative. Showing them the first label would tell a reader
 * to disregard guidance that still binds.
 */
export type RepealLabel =
  | "none"
  | "no_longer_in_force"
  | "concerns_repealed_provision";

export interface SectionMappingRef {
  from_code: string;
  from_section: string;
  to_code: string;
  to_section: string;
  subject?: string;
  /** True where the replacement is a different offence, not a renumbering. */
  ingredients_changed?: boolean;
  note?: string;
}

export type CurrentLawStatus =
  | "current"
  | "superseded"
  | "repealed"
  | "status_unverified"
  | "not_applicable";

export interface User {
  id: string;
  name: string;
  email: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

export interface AdminOverview {
  users_total: number;
  police_active: number;
  advocates_active: number;
  staged_intakes: number;
  validated_intakes: number;
  published_intakes: number;
  audit_events: number;
}

export interface AdminManagedUser extends User {
  case_count: number;
}

export interface AdminUserList {
  users: AdminManagedUser[];
  total: number;
}

export interface CorpusIntake {
  id: string;
  storage_object_id: string;
  corpus_source_id: string | null;
  title: string;
  source_type: "act" | "judgment" | "notification";
  jurisdiction: string;
  authority: string | null;
  source_url: string;
  status: "staged" | "validated" | "rejected" | "published";
  filename: string;
  file_size: number;
  sha256: string;
  validation_summary: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface CorpusIntakeList {
  intakes: CorpusIntake[];
  total: number;
}

export interface AuditEvent {
  id: string;
  actor_name: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  metadata: Record<string, unknown>;
  timestamp: string;
}

export interface AuditEventList {
  events: AuditEvent[];
  total: number;
}

export interface RetrievalHit {
  point_id: string;
  payload: {
    chunk_id?: string;
    text?: string;
    source_type?: string;
    title?: string;
    act_name?: string;
    section?: string;
    court?: string;
    jurisdiction?: string;
    decision_date?: string;
    decision_year?: number;
    page_start?: number;
    page_end?: number;
    heading_path?: string[];
    document_id?: string;
    canonical_document_id?: string;
    corpus_tier?: string;
    verified_official?: boolean;
    quality_status?: string;
    is_current?: boolean;
    [key: string]: unknown;
  };
  dense_score: number | null;
  sparse_score: number | null;
  fused_score: number;
  reranker_score: number;
}

export interface RetrievalResponse {
  query: string;
  results: RetrievalHit[];
}

export interface ScopedRetrievalResponse extends RetrievalResponse {
  mode: "general" | "case_specific";
  authorized_case_ids: string[];
}

export interface LegalCase {
  id: string;
  owner_id: string;
  role_type: "police" | "advocate";
  title: string;
  status: "open" | "closed" | "archived";
  created_at: string;
}

export interface CaseListResponse {
  cases: LegalCase[];
  total: number;
}

export interface StorageObject {
  id: string;
  case_id: string;
  original_filename: string;
  content_type: string;
  file_size: number;
  sha256: string;
}

export interface CaseDocumentIndexResponse {
  document_id: string;
  storage_object_id: string;
  case_id: string;
  doc_type: string;
  pages: number;
  chunks: number;
}

export interface GeneratedDocumentSummary {
  id: string;
  case_id: string;
  doc_type: string;
  version: number;
  status: string;
  created_at: string;
  missing_field_count: number;
  authority_count: number;
}

export interface GeneratedDocumentList {
  documents: GeneratedDocumentSummary[];
}

export interface CaseDocumentSummary {
  document_id: string;
  storage_object_id: string | null;
  filename: string;
  doc_type: string;
  uploaded_at: string;
  sha256: string | null;
  page_count: number;
  chunk_count: number;
}

export interface CaseDocumentListResponse {
  documents: CaseDocumentSummary[];
  total: number;
}

export interface SourceEvidence {
  point_id: string;
  chunk_id: string;
  title: string;
  source_type: string;
  section: string | null;
  page_start: number;
  page_end: number;
  excerpt: string;
  relevance_score: number | null;
  verification_status: "verified" | "partial" | "unverified";
  current_status: CurrentLawStatus;
  replaced_by?: string | null;
  repealed_on?: string | null;
  repeal_label?: RepealLabel;
  section_mappings?: SectionMappingRef[];
  unmapped_repealed_provisions?: string[];
  mapping_review_status?: string | null;
  scope: "global" | "private_case";
}

export interface DocumentFinding {
  text: string;
  severity: "information" | "review" | "high";
  evidence: SourceEvidence[];
}

export interface ApplicableSection {
  label: string;
  rationale: string;
  evidence: SourceEvidence;
}

export interface DocumentAnalysisResponse {
  id: string;
  case_id: string;
  document_id: string;
  version: number;
  summary: string;
  key_clauses: DocumentFinding[];
  risks: DocumentFinding[];
  applicable_sections: ApplicableSection[];
  rejected_section_count: number;
  analyzed_chunk_count: number;
  total_chunk_count: number;
  partial_review: boolean;
  disclaimer: string;
  created_at: string;
}

export interface SourceInspectorResponse {
  point_id: string;
  chunk_id: string;
  scope: "global" | "private_case";
  source_title: string;
  source_type: string;
  act_or_judgment: string | null;
  section: string | null;
  page_start: number;
  page_end: number;
  retrieved_passage: string;
  retrieval_score: number | null;
  verification_status: "verified" | "partial" | "unverified";
  current_status: CurrentLawStatus;
  replaced_by?: string | null;
  repealed_on?: string | null;
  repeal_label?: RepealLabel;
  section_mappings?: SectionMappingRef[];
  unmapped_repealed_provisions?: string[];
  mapping_review_status?: string | null;
  case_id: string | null;
  document_id: string | null;
  storage_object_id: string | null;
  corpus_tier: string | null;
  verified_official: boolean | null;
}

export interface DraftAuthority {
  chunk_id: string;
  title: string;
  section?: string | null;
  page_start: number;
  page_end: number;
  excerpt: string;
  reranker_score: number;
}

export interface FIRDraftResponse {
  id: string;
  case_id: string;
  doc_type: "fir";
  version: number;
  status: "draft" | "incomplete";
  facts: Record<string, unknown>;
  missing_fields: string[];
  authorities: DraftAuthority[];
  rendered_text: string;
  disclaimer: string;
  created_at: string;
}

export interface StrategyPoint {
  category: string;
  point: string;
  source_chunk_ids: string[];
  verification: "yes" | "partial";
  verification_reason: string;
}

export interface DefenceAnalysisResponse {
  summary: string;
  points: StrategyPoint[];
  citations: AgentCitation[];
  confidence_score: number;
  evidence_strength: "strong" | "moderate" | "insufficient";
  rejected_point_count: number;
  disclaimer: string;
}

export interface PipelineTimings {
  embedding_ms: number;
  qdrant_ms: number;
  reranking_ms: number;
  generation_ms: number;
  total_ms: number;
}

export interface AgentCitation {
  number: number;
  chunk_id: string;
  title: string;
  source_type: string;
  page_start: number;
  page_end: number;
  court?: string | null;
  act_name?: string | null;
  section?: string | null;
  source_url?: string | null;
  excerpt: string;
  retrieval_score?: number | null;
  verification_status?: "verified" | "partial" | "unverified";
  current_status?: CurrentLawStatus;
  replaced_by?: string | null;
  repealed_on?: string | null;
  repeal_label?: RepealLabel;
  section_mappings?: SectionMappingRef[];
  unmapped_repealed_provisions?: string[];
  mapping_review_status?: string | null;
}

export type RequestedResponseMode = "auto" | "fast" | "deep";
export type SelectedResponseMode = "fast" | "deep";

export interface PipelineStageMetric {
  sequence: number;
  stage: string;
  retry_index: number;
  duration_ms: number;
  inputs: Record<string, unknown>;
  outputs: Record<string, unknown>;
  llm_calls: Array<Record<string, unknown>>;
}

export interface ChatQueryResponse {
  session_id: string;
  /** Absent on an escalation placeholder, which persists no answer yet. */
  message_id: string | null;
  answer: string;
  citations: AgentCitation[];
  confidence_score: number;
  evidence_strength: "strong" | "moderate" | "insufficient";
  /** One row per published section. Empty for a Fast brief and for an
   *  abstention, neither of which has verified sections to grade. */
  section_confidence: SectionConfidence[];
  intent: Record<string, unknown>;
  agent_trace: Array<{ node: string; details: Record<string, unknown> }>;
  response_mode: SelectedResponseMode;
  requested_mode: RequestedResponseMode;
  routing_reason: string;
  routing_signals: string[];
  timings_ms: Record<string, unknown>;
  pipeline_metrics: PipelineStageMetric[];
  latency_target_ms: number;
  target_met: boolean | null;
  delivery_state: "complete" | "searching_more_thoroughly";
  job_id: string | null;
  escalation_threshold: number | null;
}

export interface DeepReviewJob {
  id: string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  progress: number;
  result: {
    session_id: string;
    message_id: string;
    answer: string;
    citations: AgentCitation[];
    confidence_score: number;
    evidence_strength: "strong" | "moderate" | "insufficient";
    intent: Record<string, unknown>;
    agent_trace: Array<{ node: string; details: Record<string, unknown> }>;
    timings_ms: Record<string, unknown>;
    pipeline_metrics: PipelineStageMetric[];
  } | null;
  error_code: string | null;
  error_message: string | null;
  /** What the job is doing right now, in citizen-readable words. */
  stage: string | null;
  stage_label: string | null;
}

/** A sidebar row from GET /chat/sessions. Carries no message bodies. */
export interface ChatSessionSummary {
  id: string;
  title: string;
  case_id: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
  last_message_preview: string | null;
}

export interface ChatSessionListResponse {
  items: ChatSessionSummary[];
  next_cursor: string | null;
}

export interface StoredChatMessage {
  id: string;
  role: string;
  content: string;
  citations: AgentCitation[];
  confidence_score: number | null;
  created_at: string;
}

export interface StoredChatSession {
  id: string;
  title: string;
  case_id: string | null;
  created_at: string;
  messages: StoredChatMessage[];
}

export interface IngestionProgress {
  total_documents: number;
  physical_documents: number;
  canonical_documents: number;
  completed_documents: number;
  remaining_documents: number;
  total_chunks_indexed: number;
  chunks_on_disk: number;
  percent: number;
  status: "complete" | "in_progress";
  validation_status: "pass" | "failed";
  qdrant_points: number;
  extended_points: number;
  global_points: number;
}

export interface ChatMessage {
  documents?: CitizenDocument[];
  stopped?: boolean;
  clientElapsedMs?: number;
  category?: string;
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: AgentCitation[];
  confidenceScore?: number;
  evidenceStrength?: "strong" | "moderate" | "insufficient";
  sectionConfidence?: SectionConfidence[];
  timestamp: number;
  loading?: boolean;
  error?: string;
  responseMode?: SelectedResponseMode;
  requestedMode?: RequestedResponseMode;
  routingReason?: string;
  routingSignals?: string[];
  agentLabel?: string;
  timingsMs?: Record<string, unknown>;
  pipelineMetrics?: PipelineStageMetric[];
  latencyTargetMs?: number;
  targetMet?: boolean | null;
  /** Live Deep-review state, so a multi-minute wait is legible. */
  stageLabel?: string | null;
  jobProgress?: number | null;
  /** Fast passages shown while a Deep escalation runs. Not yet verified. */
  provisional?: boolean;
  /** Server message id, required to attach feedback. */
  messageId?: string;
}

export interface CitizenDocument {
  id: string;
  filename: string;
  media_type: string;
  pages: Array<{ page: number; text: string }>;
  truncated: boolean;
}

export interface ChatSession {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: number;
  updatedAt: number;
}

export type OffenceGravity = "death_life_or_ten_years_or_more" | "other" | "unknown";

export interface InvestigationFacts {
  information_recorded_at: string | null;
  arrested_at: string | null;
  first_remand_at: string | null;
  accused_produced_at: string | null;
  death_occurred_at: string | null;
  preliminary_enquiry_started_at: string | null;
  gravity: OffenceGravity;
  is_listed_sexual_offence: boolean;
  is_unnatural_death: boolean;
}

export interface StoredInvestigationFacts extends InvestigationFacts {
  case_id: string;
  updated_at: string;
}

export interface InvestigationDeadline {
  key: string;
  obligation: string;
  provision: string;
  due_at: string | null;
  consequence: string;
  computed_from: string;
  is_earliest_possible: boolean;
  undetermined_because: string;
  /** null when the deadline could not be computed. Never false in that case:
   *  false is a compliance finding, and none was made. */
  is_breached: boolean | null;
}

export interface InvestigationTimeline {
  evaluated_at: string;
  deadlines: InvestigationDeadline[];
  breached: string[];
  undetermined: string[];
}

export interface SectionConfidence {
  section: string;
  claims: number;
  sources: number;
  authority: string[];
  currency_unverified: boolean;
  confidence: "strong" | "moderate" | "limited";
  /** Why it is graded this way, in the words the grader used. Shown rather
   *  than summarised: "grounded in a single source" is the actionable part,
   *  and a bare label invites the reader to supply their own reason. */
  reason: string;
}

export type PoliceAction = "arrest" | "search_and_seizure" | "case_diary" | "final_report";
export type ComplianceStatus = "satisfied" | "not_satisfied" | "not_recorded";

export interface ComplianceItem {
  key: string;
  requirement: string;
  provision: string;
  consequence: string;
  status: ComplianceStatus;
  applies_because: string;
}

export interface ComplianceChecklist {
  action: PoliceAction;
  items: ComplianceItem[];
  /** Positively not done. An item nobody confirmed is in not_recorded. */
  outstanding: string[];
  not_recorded: string[];
}

export type AuthorityFinding =
  | "still_current"
  | "renumbered"
  | "elements_changed"
  | "not_re_enacted"
  | "no_mapping_known"
  | "not_checked";

export interface CitationCheck {
  citation: string;
  code: string;
  section: string;
  finding: AuthorityFinding;
  successors: string[];
  advice: string;
  needs_attention: boolean;
}

export interface AuthorityCheckResult {
  checked: CitationCheck[];
  needs_attention: number;
  not_re_enacted: number;
  /** Recognised but outside the 2023 concordance. Surfaced so a partial
   *  check is not mistaken for a complete one. */
  not_checked: number;
}
