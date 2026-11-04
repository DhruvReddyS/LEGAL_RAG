import { request } from "@/lib/api";
import type { DefenceAnalysisResponse } from "@/lib/types";
import type {
  BailAssessment,
  BriefContent,
  CalendarEvent,
  ComparisonContent,
  DebateProgress,
  DebateRow,
  DraftContent,
  DraftTemplateInfo,
  JudgmentCatalogue,
  LimitationArticle,
  LimitationResult,
  OpponentResult,
  PrecedentResult,
  TreatmentResult,
  WorkDetail,
  WorkSummary,
} from "@/lib/types-advocate";

const post = <T,>(path: string, body: unknown, headers?: Record<string, string>) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body), headers });
const caseTool = (caseId: string, rest: string) => `/cases/${encodeURIComponent(caseId)}/advocate/${rest}`;

export const assessBail = (caseId: string, body: Record<string, unknown>) =>
  post<BailAssessment>(caseTool(caseId, "bail/assess"), body);

export const listDraftTemplates = () => request<{ templates: DraftTemplateInfo[] }>("/advocate/draft-templates");
export const createAdvocateDraft = (caseId: string, body: { draft_type: string; fields: Record<string, string>; facts: string; instructions?: string }) =>
  post<WorkDetail<DraftContent>>(caseTool(caseId, "drafts"), body);

export const calendarAcrossCases = () => request<{ today: string; events: CalendarEvent[] }>("/advocate/calendar");
export const caseCalendar = (caseId: string) => request<{ today: string; events: CalendarEvent[] }>(caseTool(caseId, "calendar"));
export const addCalendarEvent = (caseId: string, body: { kind: string; title: string; due_on: string; notes?: string; basis?: Record<string, unknown> }) =>
  post<CalendarEvent>(caseTool(caseId, "calendar"), body);
export const updateCalendarEvent = (caseId: string, eventId: string, body: { completed?: boolean; due_on?: string; title?: string; notes?: string | null }) =>
  request<CalendarEvent>(caseTool(caseId, `calendar/${encodeURIComponent(eventId)}`), { method: "PATCH", body: JSON.stringify(body) });
export const deleteCalendarEvent = (caseId: string, eventId: string) =>
  request<void>(caseTool(caseId, `calendar/${encodeURIComponent(eventId)}`), { method: "DELETE" });
export const listLimitationArticles = () => request<{ articles: LimitationArticle[]; scope_note: string }>("/advocate/limitation-articles");
export const computeLimitation = (caseId: string, body: { article: string; runs_from: string; excluded_days: number; add_to_calendar?: boolean; title?: string }) =>
  post<LimitationResult>(caseTool(caseId, "calendar/limitation"), body);

export const createBrief = (caseId: string, body: { kind: "brief" | "synopsis"; document_ids: string[]; focus?: string }) =>
  post<WorkDetail<BriefContent>>(caseTool(caseId, "briefs"), body);

export const heldJudgments = () => request<JudgmentCatalogue>("/advocate/judgments");
export const searchPrecedents = (body: { query: string; holding?: string; court?: string; year_from?: number; year_to?: number }) =>
  post<PrecedentResult>("/advocate/precedents", body);
export const checkTreatment = (reference: string) => post<TreatmentResult>("/advocate/treatment", { reference });

export const checkOpponent = (caseId: string, body: { text?: string; document_id?: string; save?: boolean }) =>
  post<OpponentResult>(caseTool(caseId, "opponent-check"), body);

export const compareJudgments = (caseId: string, body: { first_judgment_id: string; second_judgment_id?: string; matter_facts?: string; focus?: string }) =>
  post<WorkDetail<ComparisonContent>>(caseTool(caseId, "compare"), body);

export const startDebate = (caseId: string, body: { proposition: string; facts?: string; rounds: number }, idempotencyKey: string) =>
  post<{ id: string }>(caseTool(caseId, "debates"), body, { "Idempotency-Key": idempotencyKey });
export const listDebates = (caseId: string) => request<{ debates: DebateRow[] }>(caseTool(caseId, "debates"));
export const readDebate = (caseId: string, jobId: string) => request<DebateProgress>(caseTool(caseId, `debates/${encodeURIComponent(jobId)}`));
export const cancelDebate = (jobId: string) => post<unknown>(`/jobs/${encodeURIComponent(jobId)}/cancel`, {});

export const listWork = (caseId: string) => request<{ work: WorkSummary[] }>(caseTool(caseId, "work"));
export const readWork = <T,>(caseId: string, workId: string) => request<WorkDetail<T>>(caseTool(caseId, `work/${encodeURIComponent(workId)}`));

export const listDefenceAnalyses = (caseId: string) =>
  request<{ analyses: WorkSummary[] }>(`/cases/${encodeURIComponent(caseId)}/strategy/defence-analyses`);
export const readDefenceAnalysis = (caseId: string, analysisId: string) =>
  request<DefenceAnalysisResponse>(`/cases/${encodeURIComponent(caseId)}/strategy/defence-analyses/${encodeURIComponent(analysisId)}`);
