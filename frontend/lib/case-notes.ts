import { request } from "./api";

export interface CaseNote {
  id: string;
  case_id: string;
  body: string;
  created_at: string;
  updated_at: string;
}

export const MAX_NOTE_CHARS = 10_000;

export function listCaseNotes(caseId: string, signal?: AbortSignal): Promise<{ notes: CaseNote[] }> {
  return request(`/cases/${caseId}/notes`, { signal });
}

export function createCaseNote(caseId: string, body: string): Promise<CaseNote> {
  return request(`/cases/${caseId}/notes`, { method: "POST", body: JSON.stringify({ body }) });
}

export function editCaseNote(caseId: string, noteId: string, body: string): Promise<CaseNote> {
  return request(`/cases/${caseId}/notes/${noteId}`, { method: "PUT", body: JSON.stringify({ body }) });
}

export function deleteCaseNote(caseId: string, noteId: string): Promise<void> {
  return request(`/cases/${caseId}/notes/${noteId}`, { method: "DELETE" });
}
