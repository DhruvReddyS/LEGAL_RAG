/**
 * The chat shell's decisions, pulled out of page.tsx so they can be tested.
 * F17 history sync, F19 poll retry, F24 paging, F27 safety label.
 */
import type { ChatMessage, StoredChatMessage } from "./types";

/** F17: a placeholder or a failed load must never be copied into the sidebar row. */
export function isDurableConversation(messages: ChatMessage[]): boolean {
  if (!messages.length) return false;
  return !messages.some(message => message.loading || message.error);
}

type HistoryRow = { id: string; sessionId: string | null; title: string; messages: ChatMessage[]; customTitle?: boolean; pinned?: boolean; updatedAt?: number; caseId?: string | null; messageCount?: number; preview?: string };

/**
 * F17: opening a chat is not activity. The row only moves up when the
 * conversation actually grew; otherwise it keeps its place and its timestamp.
 */
export function syncHistoryRow<T extends HistoryRow>(
  current: T[],
  live: { activeChatId: string; sessionId: string | null; messages: ChatMessage[]; caseId: string | null },
  now: number,
): T[] {
  if (!isDurableConversation(live.messages)) return current;
  const existing = current.find(item => item.id === live.activeChatId || (live.sessionId && item.sessionId === live.sessionId));
  const grew = !existing || (existing.messageCount ?? existing.messages.length) < live.messages.length;
  const title = existing?.customTitle ? existing.title : existing?.title && !grew ? existing.title : live.messages.find(message => message.role === "user")?.content.slice(0, 90) || existing?.title || "Untitled chat";
  const row = {
    ...(existing ?? {}),
    id: existing?.id ?? live.activeChatId,
    title,
    messages: live.messages,
    sessionId: live.sessionId,
    updatedAt: grew ? now : existing?.updatedAt ?? now,
    messageCount: Math.max(live.messages.length, existing?.messageCount ?? 0),
    caseId: existing?.caseId ?? live.caseId,
  } as T;
  if (!existing) return [row, ...current];
  return grew ? [row, ...current.filter(item => item !== existing)] : current.map(item => (item === existing ? row : item));
}

/** F24: a later page never duplicates what is already listed. */
export function mergeHistoryPage<T extends { id: string }>(current: T[], page: T[]): T[] {
  const known = new Set(current.map(item => item.id));
  return [...current, ...page.filter(item => !known.has(item.id))];
}

/** F19: only what can pass by itself is retried. A refused or missing job is final. */
export function isTransientPollError(error: unknown): boolean {
  const status = (error as { status?: unknown } | null)?.status;
  if (typeof status !== "number") return true; // fetch threw: the network dropped
  return status === 429 || status >= 500;
}

export const MAX_POLL_FAILURES = 8;

export function pollDelayMs(consecutiveFailures: number): number {
  if (consecutiveFailures <= 0) return 1000;
  return Math.min(1000 * 2 ** consecutiveFailures, 15_000);
}

/** F27: a safety answer did not come from sources, so it must not read like a ranked passage. */
export type SafetyKind = "emergency" | "refusal";

export function safetyKind(message: Pick<ChatMessage, "routingReason"> & { safetyKind?: string | null }): SafetyKind | null {
  const kind = message.safetyKind ?? (message.routingReason?.startsWith("safety_") ? message.routingReason.slice(7) : null);
  return kind === "emergency" || kind === "refusal" ? kind : null;
}

/** Not a gap in the law held: the question is about something else, so nobody to refer to. */
export function isOutOfScope(message: Pick<ChatMessage, "routingReason"> & { safetyKind?: string | null }): boolean {
  return message.safetyKind === "out_of_scope" || message.routingReason === "safety_out_of_scope";
}

/** PLAT-09: an answer with no evidence routes to a person. */
export function shouldOfferHuman(message: Pick<ChatMessage, "evidenceStrength" | "citations" | "error">): boolean {
  if (message.error) return false;
  return message.evidenceStrength === "insufficient" || !(message.citations?.length);
}

/**
 * A stored message back on screen. The grade and the lane are not stored, so only
 * what the score can honestly say comes back: a zero is an abstention. Section
 * grades and a safety label come from their own stored row (F27, F28).
 */
export function restoreStoredMessages(stored: StoredChatMessage[]): ChatMessage[] {
  return stored.map(message => ({
    id: message.id,
    messageId: message.id,
    role: message.role === "user" ? "user" : "assistant",
    content: message.content,
    citations: message.citations,
    confidenceScore: message.confidence_score ?? undefined,
    evidenceStrength: message.confidence_score === 0 ? "insufficient" : undefined,
    responseMode: undefined,
    sectionConfidence: message.section_confidence?.length ? message.section_confidence : undefined,
    safetyKind: message.safety_kind ?? undefined,
    timestamp: Date.parse(message.created_at),
  }));
}

const draftKey = "corpusil-chat-draft";

/** F25: what was being typed survives having to sign in again. */
export function saveDraft(storage: Pick<Storage, "setItem" | "removeItem">, value: string): void {
  try {
    if (value.trim()) storage.setItem(draftKey, value.slice(0, 4000));
    else storage.removeItem(draftKey);
  } catch { /* storage disabled */ }
}

export function readDraft(storage: Pick<Storage, "getItem">): string {
  try { return storage.getItem(draftKey) ?? ""; } catch { return ""; }
}
