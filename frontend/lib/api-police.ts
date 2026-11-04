import { request } from "@/lib/api";
import type {
  CaseFile,
  ComplianceRecordList,
  ComplianceRecordStatus,
  DiaryEntry,
  DiaryResponse,
  DraftSummary,
  DraftType,
  EvidenceItem,
  MyUnit,
  OffenceAssessment,
  OffenceCatalogueEntry,
  ElementState,
  PoliceDraft,
  PoliceUnit,
  RegisterFilters,
  RegisterResponse,
  RegisterRow,
  RemandSummary,
  SearchQuestions,
  SearchRecordRow,
  SupervisedUnit,
  Witness,
} from "@/lib/types-police";
import { registerQuery } from "@/lib/police-presentation";

const json = (method: string, body: unknown): RequestInit => ({ method, body: JSON.stringify(body) });
const caseBase = (caseId: string) => `/cases/${caseId}/police`;

export function getRegister(filters: Partial<RegisterFilters> = {}): Promise<RegisterResponse> {
  const query = registerQuery(filters);
  return request<RegisterResponse>(`/police/deadlines${query ? `?${query}` : ""}`);
}

export function recordCompletion(caseId: string, key: string, completedAt: string, note: string): Promise<RegisterRow> {
  return request<RegisterRow>(
    `${caseBase(caseId)}/deadlines/${encodeURIComponent(key)}/completion`,
    json("PUT", { completed_at: completedAt, note: note || null }),
  );
}

export function withdrawCompletion(caseId: string, key: string): Promise<void> {
  return request<void>(`${caseBase(caseId)}/deadlines/${encodeURIComponent(key)}/completion`, { method: "DELETE" });
}

export function getComplianceRecords(caseId: string, action: string): Promise<ComplianceRecordList> {
  return request<ComplianceRecordList>(`${caseBase(caseId)}/compliance-records?action=${action}`);
}

export function writeComplianceRecord(
  caseId: string,
  action: string,
  key: string,
  body: { status?: ComplianceRecordStatus; occurred_at: string | null; evidence_note: string | null; evidence_item_id: string | null },
): Promise<ComplianceRecordList> {
  return request<ComplianceRecordList>(`${caseBase(caseId)}/compliance-records/${action}/${key}`, json("PUT", body));
}

export async function listEvidence(caseId: string): Promise<EvidenceItem[]> {
  return (await request<{ items: EvidenceItem[] }>(`${caseBase(caseId)}/evidence`)).items;
}

export function addEvidence(caseId: string, body: Record<string, unknown>): Promise<EvidenceItem> {
  return request<EvidenceItem>(`${caseBase(caseId)}/evidence`, json("POST", body));
}

export function updateEvidence(caseId: string, itemId: string, body: Record<string, unknown>): Promise<EvidenceItem> {
  return request<EvidenceItem>(`${caseBase(caseId)}/evidence/${itemId}`, json("PATCH", body));
}

export function addCustodyEvent(caseId: string, itemId: string, body: Record<string, unknown>): Promise<EvidenceItem> {
  return request<EvidenceItem>(`${caseBase(caseId)}/evidence/${itemId}/custody`, json("POST", body));
}

export async function listWitnesses(caseId: string): Promise<Witness[]> {
  return (await request<{ witnesses: Witness[] }>(`${caseBase(caseId)}/witnesses`)).witnesses;
}

export function addWitness(caseId: string, body: Record<string, unknown>): Promise<Witness> {
  return request<Witness>(`${caseBase(caseId)}/witnesses`, json("POST", body));
}

export function updateWitness(caseId: string, witnessId: string, body: Record<string, unknown>): Promise<Witness> {
  return request<Witness>(`${caseBase(caseId)}/witnesses/${witnessId}`, json("PATCH", body));
}

export function getSearchQuestions(): Promise<SearchQuestions> {
  return request<SearchQuestions>("/police/search-questions");
}

export async function listSearches(caseId: string): Promise<SearchRecordRow[]> {
  return (await request<{ searches: SearchRecordRow[] }>(`${caseBase(caseId)}/searches`)).searches;
}

export function saveSearch(caseId: string, searchId: string | null, body: Record<string, unknown>): Promise<SearchRecordRow> {
  return searchId
    ? request<SearchRecordRow>(`${caseBase(caseId)}/searches/${searchId}`, json("PUT", body))
    : request<SearchRecordRow>(`${caseBase(caseId)}/searches`, json("POST", body));
}

export async function getOffenceCatalogue(): Promise<OffenceCatalogueEntry[]> {
  return (await request<{ offences: OffenceCatalogueEntry[] }>("/police/offences")).offences;
}

export async function listAssessments(caseId: string): Promise<OffenceAssessment[]> {
  return (await request<{ assessments: OffenceAssessment[] }>(`${caseBase(caseId)}/offences`)).assessments;
}

export function writeAssessment(
  caseId: string,
  offenceKey: string,
  elements: Record<string, { state: ElementState; evidence_item_ids: string[]; witness_ids: string[]; note: string }>,
): Promise<OffenceAssessment> {
  return request<OffenceAssessment>(`${caseBase(caseId)}/offences/${offenceKey}`, json("PUT", { elements }));
}

export function removeAssessment(caseId: string, offenceKey: string): Promise<void> {
  return request<void>(`${caseBase(caseId)}/offences/${offenceKey}`, { method: "DELETE" });
}

export function getRemand(caseId: string): Promise<RemandSummary> {
  return request<RemandSummary>(`${caseBase(caseId)}/remand`);
}

export function addRemand(caseId: string, body: Record<string, unknown>): Promise<RemandSummary> {
  return request<RemandSummary>(`${caseBase(caseId)}/remand`, json("POST", body));
}

export function removeRemand(caseId: string, periodId: string): Promise<RemandSummary> {
  return request<RemandSummary>(`${caseBase(caseId)}/remand/${periodId}`, { method: "DELETE" });
}

export function getDiary(caseId: string): Promise<DiaryResponse> {
  return request<DiaryResponse>(`${caseBase(caseId)}/diary`);
}

export function addDiaryEntry(caseId: string, body: Partial<DiaryEntry>): Promise<DiaryResponse> {
  return request<DiaryResponse>(`${caseBase(caseId)}/diary`, json("POST", body));
}

export async function listDrafts(caseId: string): Promise<DraftSummary[]> {
  return (await request<{ drafts: DraftSummary[] }>(`${caseBase(caseId)}/drafts`)).drafts;
}

export function createDraft(caseId: string, draftType: DraftType, inputs: Record<string, string>): Promise<PoliceDraft> {
  return request<PoliceDraft>(`${caseBase(caseId)}/drafts`, json("POST", { draft_type: draftType, inputs }));
}

export function readDraft(caseId: string, draftId: string): Promise<PoliceDraft> {
  return request<PoliceDraft>(`${caseBase(caseId)}/drafts/${draftId}`);
}

export function getCaseFile(caseId: string, options: { contact: boolean; drafts: boolean }): Promise<CaseFile> {
  const params = new URLSearchParams({
    include_witness_contact: String(options.contact),
    include_drafts: String(options.drafts),
  });
  return request<CaseFile>(`${caseBase(caseId)}/case-file?${params}`);
}

export async function getAccessLog(caseId: string): Promise<{ at: string; who: string; what: string }[]> {
  return (await request<{ entries: { at: string; who: string; what: string }[] }>(`${caseBase(caseId)}/access-log`)).entries;
}

export async function getMyUnits(): Promise<MyUnit[]> {
  return (await request<{ units: MyUnit[] }>("/police/my-units")).units;
}

export function getSupervisedUnit(unitId: string): Promise<SupervisedUnit> {
  return request<SupervisedUnit>(`/police/supervision/units/${unitId}`);
}

export async function listUnits(): Promise<PoliceUnit[]> {
  return (await request<{ units: PoliceUnit[] }>("/police/units")).units;
}

export function createUnit(name: string): Promise<PoliceUnit> {
  return request<PoliceUnit>("/police/units", json("POST", { name }));
}

export function setUnitMember(unitId: string, email: string, role: "member" | "supervisor"): Promise<PoliceUnit> {
  return request<PoliceUnit>(`/police/units/${unitId}/members`, json("PUT", { email, role }));
}

export function removeUnitMember(unitId: string, userId: string): Promise<PoliceUnit> {
  return request<PoliceUnit>(`/police/units/${unitId}/members/${userId}`, { method: "DELETE" });
}
