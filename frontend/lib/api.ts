import type {
  ChatQueryResponse,
  CaseDocumentIndexResponse,
  CaseListResponse,
  DefenceAnalysisResponse,
  FIRDraftResponse,
  IngestionProgress,
  LegalCase,
  RetrievalResponse,
  ScopedRetrievalResponse,
  StorageObject,
  User,
  RequestedResponseMode,
  AdminOverview,
  AdminManagedUser,
  AdminUserList,
  CorpusIntake,
  CorpusIntakeList,
  AuditEventList,
  CaseDocumentListResponse,
  DocumentAnalysisResponse,
  SourceInspectorResponse,
} from "./types";

const CONFIGURED_API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function apiUrl(): string {
  if (typeof window === "undefined") {
    return CONFIGURED_API_URL;
  }

  // A packaged Tauri window uses a localhost-shaped custom origin. Reusing
  // that origin's protocol would produce an invalid API URL such as
  // `tauri://localhost:8000`, so desktop builds must use the configured HTTP
  // endpoint explicitly.
  const isTauri =
    "__TAURI_INTERNALS__" in window ||
    window.location.protocol === "tauri:" ||
    window.location.hostname === "tauri.localhost";

  if (
    !isTauri &&
    (window.location.hostname === "localhost" ||
      window.location.hostname.endsWith(".localhost") ||
      window.location.hostname.startsWith("127."))
  ) {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }
  return CONFIGURED_API_URL;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  retryAuth = true,
): Promise<T> {
  const isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;
  const headers: Record<string, string> = {
    ...(!isFormData ? { "Content-Type": "application/json" } : {}),
    ...(options.headers as Record<string, string>),
  };

  const baseUrl = apiUrl();
  let response = await fetch(`${baseUrl}${path}`, {
    ...options,
    headers,
    credentials: "include",
  });

  if (response.status === 401 && retryAuth && !path.startsWith("/auth/")) {
    const refreshed = await fetch(`${baseUrl}/auth/cookie/refresh`, {
      method: "POST",
      credentials: "include",
    });
    if (refreshed.ok) {
      response = await fetch(`${baseUrl}${path}`, {
        ...options,
        headers,
        credentials: "include",
      });
    }
  }

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? body.message ?? detail;
      if (Array.isArray(detail)) {
        detail = detail.map((d) => d.msg ?? String(d)).join(", ");
      }
    } catch {
      // ignore parse errors
    }
    throw new ApiError(String(detail), response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export async function login(
  email: string,
  password: string,
): Promise<User> {
  return request<User>("/auth/cookie/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  }, false);
}

export async function register(
  name: string,
  email: string,
  password: string,
): Promise<User> {
  return request<User>("/auth/cookie/register", {
    method: "POST",
    body: JSON.stringify({ name, email, password, role: "citizen" }),
  }, false);
}

export async function refreshSession(): Promise<User> {
  return request<User>("/auth/cookie/refresh", {
    method: "POST",
  }, false);
}

export async function logout(): Promise<void> {
  return request<void>("/auth/cookie/logout", { method: "POST" }, false);
}

export async function getMe(): Promise<User> {
  return request<User>("/auth/me", {}, false);
}

export async function searchCorpus(
  query: string,
  resultLimit = 5,
): Promise<RetrievalResponse> {
  return request<RetrievalResponse>(
    "/retrieval/search",
    {
      method: "POST",
      body: JSON.stringify({
        query,
        filters: { corpus_tiers: ["gold", "extended"] },
        candidate_limit: 20,
        result_limit: resultLimit,
      }),
    },
  );
}

export async function chatWithCorpus(
  query: string,
  sessionId?: string | null,
  responseMode: RequestedResponseMode = "auto",
): Promise<ChatQueryResponse> {
  return request<ChatQueryResponse>("/chat/query", {
    method: "POST",
    body: JSON.stringify({
      query,
      session_id: sessionId ?? null,
      response_mode: responseMode,
    }),
  });
}

export async function getIngestionProgress(): Promise<IngestionProgress> {
  return request<IngestionProgress>("/ingestion/progress");
}

export async function healthCheck(): Promise<{ status: string }> {
  return request<{ status: string }>("/health");
}

export async function getAdminOverview(): Promise<AdminOverview> {
  return request<AdminOverview>("/admin/overview");
}

export async function listAdminUsers(): Promise<AdminUserList> {
  return request<AdminUserList>("/admin/users");
}

export async function createAdminUser(payload: {
  name: string; email: string; password: string; role: "police" | "advocate";
}): Promise<AdminManagedUser> {
  return request<AdminManagedUser>("/admin/users", { method: "POST", body: JSON.stringify(payload) });
}

export async function updateAdminUser(
  userId: string,
  payload: { role?: "police" | "advocate"; is_active?: boolean },
): Promise<AdminManagedUser> {
  return request<AdminManagedUser>(`/admin/users/${userId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export async function listCorpusIntakes(): Promise<CorpusIntakeList> {
  return request<CorpusIntakeList>("/admin/corpus/intakes");
}

export async function stageCorpusIntake(payload: {
  file: File; title: string; sourceType: string; jurisdiction: string; authority: string; sourceUrl: string;
}): Promise<CorpusIntake> {
  const form = new FormData();
  form.append("file", payload.file);
  form.append("title", payload.title);
  form.append("source_type", payload.sourceType);
  form.append("jurisdiction", payload.jurisdiction);
  form.append("authority", payload.authority);
  form.append("source_url", payload.sourceUrl);
  return request<CorpusIntake>("/admin/corpus/intakes", { method: "POST", body: form });
}

export async function validateCorpusIntake(intakeId: string): Promise<CorpusIntake> {
  return request<CorpusIntake>(`/admin/corpus/intakes/${intakeId}/validate`, { method: "POST" });
}

export async function publishCorpusIntake(intakeId: string): Promise<{ intake: CorpusIntake; indexed_chunks: number; corpus_tier: "extended" }> {
  return request(`/admin/corpus/intakes/${intakeId}/publish`, { method: "POST" });
}

export async function listAuditEvents(): Promise<AuditEventList> {
  return request<AuditEventList>("/admin/audit?limit=50");
}

export async function listCases(): Promise<CaseListResponse> {
  return request<CaseListResponse>("/cases");
}

export async function createCase(title: string): Promise<LegalCase> {
  return request<LegalCase>("/cases", {
    method: "POST",
    body: JSON.stringify({ title }),
  });
}

export async function scopedSearch(
  query: string,
  mode: "general" | "case_specific",
  caseId?: string,
): Promise<ScopedRetrievalResponse> {
  const params = new URLSearchParams({ mode });
  if (mode === "case_specific" && caseId) params.set("case_id", caseId);
  return request<ScopedRetrievalResponse>(`/retrieval/scoped-search?${params}`, {
    method: "POST",
    body: JSON.stringify({
      query,
      filters: { corpus_tiers: ["gold", "extended"] },
      candidate_limit: 20,
      result_limit: 6,
    }),
  });
}

export async function uploadCaseEvidence(
  caseId: string,
  file: File,
): Promise<StorageObject> {
  const form = new FormData();
  form.append("file", file);
  return request<StorageObject>(`/cases/${caseId}/storage/objects`, {
    method: "POST",
    body: form,
  });
}

export async function indexCaseEvidence(
  caseId: string,
  objectId: string,
  docType: string,
): Promise<CaseDocumentIndexResponse> {
  return request<CaseDocumentIndexResponse>(
    `/cases/${caseId}/storage/objects/${objectId}/index`,
    { method: "POST", body: JSON.stringify({ doc_type: docType }) },
  );
}

export async function listIndexedCaseDocuments(
  caseId: string,
): Promise<CaseDocumentListResponse> {
  return request<CaseDocumentListResponse>(`/cases/${caseId}/documents/indexed`);
}

export async function analyzeCaseDocument(
  caseId: string,
  documentId: string,
  focus?: string,
): Promise<DocumentAnalysisResponse> {
  const params = new URLSearchParams({ case_id: caseId });
  return request<DocumentAnalysisResponse>(`/documents/analyze?${params}`, {
    method: "POST",
    body: JSON.stringify({ document_id: documentId, focus: focus?.trim() || null }),
  });
}

export async function getLatestDocumentAnalysis(
  caseId: string,
  documentId: string,
): Promise<DocumentAnalysisResponse> {
  const params = new URLSearchParams({ case_id: caseId, document_id: documentId });
  return request<DocumentAnalysisResponse>(`/documents/analyses/latest?${params}`);
}

export async function inspectSource(
  pointId: string,
  caseId?: string,
): Promise<SourceInspectorResponse> {
  return request<SourceInspectorResponse>(
    caseId ? `/cases/${caseId}/sources/${pointId}` : `/sources/${pointId}`,
  );
}

export async function draftFir(
  caseId: string,
  caseDescription: string,
): Promise<FIRDraftResponse> {
  return request<FIRDraftResponse>(`/cases/${caseId}/documents/draft`, {
    method: "POST",
    body: JSON.stringify({ doc_type: "fir", case_description: caseDescription }),
  });
}

export async function analyseDefence(
  caseId: string,
  caseScenario: string,
  advocatePosition?: string,
): Promise<DefenceAnalysisResponse> {
  return request<DefenceAnalysisResponse>(
    `/cases/${caseId}/strategy/defence-analysis`,
    {
      method: "POST",
      body: JSON.stringify({
        case_scenario: caseScenario,
        advocate_position: advocatePosition || null,
      }),
    },
  );
}
