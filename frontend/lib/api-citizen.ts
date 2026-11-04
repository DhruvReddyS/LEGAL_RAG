import { request } from "@/lib/api";
import type { Lang } from "./citizen-law/law";
import type { CitizenDeadline, DeadlineInput, NoticeExplanation } from "./types-citizen";

export function explainNotice(text: string, options: { plainLanguage?: boolean; language?: Lang; signal?: AbortSignal } = {}): Promise<NoticeExplanation> {
  return request<NoticeExplanation>("/citizen/tools/notice/explain", {
    method: "POST",
    signal: options.signal,
    body: JSON.stringify({ text, plain_language: Boolean(options.plainLanguage), language: options.language ?? "en" }),
  });
}

export function listDeadlines(): Promise<{ items: CitizenDeadline[]; today: string }> {
  return request("/citizen/matter/deadlines");
}

export function createDeadline(input: DeadlineInput): Promise<CitizenDeadline> {
  return request("/citizen/matter/deadlines", { method: "POST", body: JSON.stringify(input) });
}

export function updateDeadline(id: string, changes: Partial<DeadlineInput> & { completed?: boolean }): Promise<CitizenDeadline> {
  return request(`/citizen/matter/deadlines/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(changes) });
}

export function deleteDeadline(id: string): Promise<void> {
  return request(`/citizen/matter/deadlines/${encodeURIComponent(id)}`, { method: "DELETE" });
}
