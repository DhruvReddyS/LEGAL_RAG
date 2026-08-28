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
  current_status: "current" | "superseded" | "status_unverified" | "not_applicable";
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
  current_status: "current" | "superseded" | "status_unverified" | "not_applicable";
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
  current_status?: "current" | "superseded" | "status_unverified" | "not_applicable";
}

export type RequestedResponseMode = "auto" | "fast" | "deep";
export type SelectedResponseMode = "fast" | "deep";

export interface ChatQueryResponse {
  session_id: string;
  message_id: string;
  answer: string;
  citations: AgentCitation[];
  confidence_score: number;
  evidence_strength: "strong" | "moderate" | "insufficient";
  intent: Record<string, unknown>;
  agent_trace: Array<{ node: string; details: Record<string, unknown> }>;
  response_mode: SelectedResponseMode;
  requested_mode: RequestedResponseMode;
  routing_reason: string;
  routing_signals: string[];
  timings_ms: Record<string, number | boolean>;
  latency_target_ms: number;
  target_met: boolean | null;
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
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: AgentCitation[];
  confidenceScore?: number;
  evidenceStrength?: "strong" | "moderate" | "insufficient";
  timestamp: number;
  loading?: boolean;
  error?: string;
  responseMode?: SelectedResponseMode;
  requestedMode?: RequestedResponseMode;
  routingReason?: string;
  routingSignals?: string[];
  agentLabel?: string;
  timingsMs?: Record<string, number | boolean>;
  latencyTargetMs?: number;
  targetMet?: boolean | null;
}

export interface ChatSession {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: number;
  updatedAt: number;
}
