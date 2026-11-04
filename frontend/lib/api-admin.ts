import { request } from "@/lib/api";
import { toQuery } from "@/lib/admin-presentation";
import type {
  AuditFilters,
  ConsoleAudit,
  ConsoleUser,
  CorpusBrowse,
  CutoverPlan,
  EvaluationRun,
  FeedbackList,
  FeedbackTrace,
  GateRun,
  ModelConfiguration,
  QualityDashboard,
  QuarantinePreview,
  QuarantineRow,
  ReleaseDecision,
  ReleaseState,
  RetentionDryRun,
  RetentionState,
  RunComparison,
  SystemHealth,
  TriageStatus,
  UserDirectory,
  WorkQueue,
  WorkStatus,
} from "@/lib/types-admin";

const BASE = "/admin/console";

function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(`${BASE}${path}`, {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

function put<T>(path: string, body: unknown): Promise<T> {
  return request<T>(`${BASE}${path}`, { method: "PUT", body: JSON.stringify(body) });
}

export const getReleaseState = () => request<ReleaseState>(`${BASE}/release`);

export const readGateDocument = (label: string, name: string) =>
  request<{ name: string; content: string }>(
    `${BASE}/release/${encodeURIComponent(label)}/documents/${encodeURIComponent(name)}`,
  );

export const recordReleaseDecision = (body: {
  label: string;
  collection: string;
  decision: "approve" | "refuse";
  reason: string;
  override_failed_gates: boolean;
}) => post<ReleaseDecision>("/release/decisions", body);

export const getCutoverPlan = (collection: string, confirmCollection: string) =>
  post<CutoverPlan>("/release/cutover-plan", {
    collection,
    confirm_collection: confirmCollection,
  });

export const queueGateRun = (label: string, collection: string) =>
  post<GateRun>("/release/gate-runs", { label, collection, confirm: true });

export const cancelGateRun = (id: string) => post<GateRun>(`/release/gate-runs/${id}/cancel`);

export const browseCorpus = (filters: {
  q?: string;
  source_type?: string;
  domain?: string;
  currency?: string;
  queue?: WorkQueue | "";
  work_status?: WorkStatus | "";
  page?: number;
  page_size?: number;
}) => request<CorpusBrowse>(`${BASE}/corpus${toQuery(filters)}`);

export const setWorkItem = (body: {
  canonical_document_id: string;
  queue: WorkQueue;
  status: WorkStatus;
  note?: string | null;
}) => put<{ status: WorkStatus }>("/corpus/work-items", body);

export const getQualityDashboard = (days: number) =>
  request<QualityDashboard>(`${BASE}/quality?days=${days}`);

export const listFeedback = (filters: {
  rating?: "up" | "down" | "";
  status?: TriageStatus | "";
  page?: number;
  page_size?: number;
}) => request<FeedbackList>(`${BASE}/feedback${toQuery(filters)}`);

export const traceFeedback = (id: string) => request<FeedbackTrace>(`${BASE}/feedback/${id}/trace`);

export const updateTriage = (id: string, status: TriageStatus, note: string | null) =>
  put<{ status: TriageStatus }>(`/feedback/${id}/triage`, { status, note });

export const listQuarantines = (includeReleased: boolean) =>
  request<{ quarantines: QuarantineRow[] }>(
    `${BASE}/quarantine?include_released=${includeReleased}`,
  );

export const previewQuarantine = (canonicalDocumentId: string) =>
  post<QuarantinePreview>("/quarantine/preview", { canonical_document_id: canonicalDocumentId });

export const quarantineDocument = (body: {
  canonical_document_id: string;
  reason: string;
  feedback_id?: string | null;
}) => post<QuarantineRow>("/quarantine", { ...body, confirm: true });

export const releaseQuarantine = (id: string, reason: string) =>
  post<QuarantineRow>(`/quarantine/${id}/release`, { reason, confirm: true });

export const listConsoleUsers = (filters: {
  q?: string;
  role?: string;
  status?: string;
  page?: number;
  page_size?: number;
}) => request<UserDirectory>(`${BASE}/users${toQuery(filters)}`);

export const suspendUser = (id: string, reason: string) =>
  post<ConsoleUser>(`/users/${id}/suspend`, { reason, confirm: true });
export const reactivateUser = (id: string) =>
  post<ConsoleUser>(`/users/${id}/reactivate`, { confirm: true });
export const revokeUserSessions = (id: string) =>
  post<ConsoleUser>(`/users/${id}/revoke-sessions`, { confirm: true });
export const setForcePasswordReset = (id: string, required: boolean) =>
  post<ConsoleUser>(`/users/${id}/force-password-reset`, { required });
export const setMfaRequired = (id: string, required: boolean) =>
  post<ConsoleUser>(`/users/${id}/mfa-required`, { required });
export const changeUserRole = (id: string, role: string) =>
  post<ConsoleUser>(`/users/${id}/role`, { role, confirm: true });

export const getRetention = () => request<RetentionState>(`${BASE}/retention`);
export const setRetentionPolicy = (category: string, days: number | null) =>
  put<RetentionState>(`/retention/${category}`, { days });
export const runRetentionDryRun = () => post<RetentionDryRun>("/retention/dry-run");
export const runRetentionPurge = (dryRunId: string, confirmation: string) =>
  post<{ id: string; deleted: Record<string, number> }>("/retention/purge", {
    dry_run_id: dryRunId,
    confirmation,
  });

export const getModelConfiguration = () => request<ModelConfiguration>(`${BASE}/models`);
export const listEvaluationRuns = () => request<{ runs: EvaluationRun[] }>(`${BASE}/evaluations`);
export const compareEvaluationRuns = (a: string, b: string) =>
  request<RunComparison>(`${BASE}/evaluations/compare${toQuery({ a, b })}`);

export const getConsoleAudit = (filters: AuditFilters) =>
  request<ConsoleAudit>(`${BASE}/audit${toQuery({ ...filters })}`);

export const getSystemHealth = () => request<SystemHealth>(`${BASE}/health`);
