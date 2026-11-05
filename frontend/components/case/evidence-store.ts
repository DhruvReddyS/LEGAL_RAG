"use client";

import { ApiError, indexCaseEvidence, uploadCaseEvidence } from "@/lib/api";
import { evidenceRejection, processEvidenceItem, type EvidenceItem } from "@/lib/evidence-queue";

/**
 * One queue for the page, outside React, so moving to another tool or case does
 * not lose the batch. Each row keeps the case it was added to.
 */
const EMPTY: EvidenceItem[] = [];
let items: EvidenceItem[] = EMPTY;
let draining = false;
let nextId = 0;
const files = new Map<string, File>();
const listeners = new Set<() => void>();
let onIndexed: (() => void) | null = null;

function errorText(error: unknown): string {
  return error instanceof ApiError ? error.message : "The operation failed. Check the connection and try again.";
}

function commit(next: EvidenceItem[]) {
  items = next;
  listeners.forEach((listener) => listener());
}

function patch(id: string, change: Partial<EvidenceItem>) {
  commit(items.map((item) => (item.id === id ? { ...item, ...change } : item)));
}

async function drain() {
  if (draining) return;
  draining = true;
  try {
    for (;;) {
      const item = items.find((row) => row.status === "queued");
      if (!item) return;
      const file = files.get(item.id);
      if (!file) { patch(item.id, { status: "failed", detail: "This file is no longer available. Choose it again.", retryable: false }); continue; }
      const done = await processEvidenceItem(item, {
        upload: () => uploadCaseEvidence(item.caseId, file),
        index: (objectId) => indexCaseEvidence(item.caseId, objectId, item.docType),
        isRateLimited: (error) => error instanceof ApiError && error.status === 429,
        // The server judged the file itself. A session or rate problem can still clear.
        isRefusal: (error) => error instanceof ApiError && [413, 415, 422].includes(error.status),
        errorText,
        wait: (ms) => new Promise((resolve) => window.setTimeout(resolve, ms)),
        onChange: (change) => patch(item.id, change),
      });
      if (done) { files.delete(item.id); onIndexed?.(); }
    }
  } finally {
    draining = false;
  }
}

export const evidenceStore = {
  subscribe(listener: () => void) {
    listeners.add(listener);
    return () => { listeners.delete(listener); };
  },
  snapshot: () => items,
  serverSnapshot: () => EMPTY,
  /** The latest caller's refresh, kept after it unmounts: its parent's list still needs it. */
  setOnIndexed(callback: (() => void) | undefined) { onIndexed = callback ?? null; },
  enqueue(chosen: File[], caseId: string, docType: string) {
    if (!chosen.length || !caseId) return;
    const added = chosen.map((file): EvidenceItem => {
      nextId += 1;
      const id = `evidence-${nextId}`;
      const rejection = evidenceRejection(file);
      if (!rejection) files.set(id, file);
      return { id, caseId, docType, name: file.name, status: rejection ? "failed" : "queued", detail: rejection ?? "", retryable: false };
    });
    commit([...items, ...added]);
    void drain();
  },
  retry(id: string) {
    patch(id, { status: "queued", detail: "", retryable: false });
    void drain();
  },
  clearFinished(caseId: string) {
    commit(items.filter((item) => {
      const finished = item.caseId === caseId && (item.status === "done" || item.status === "failed");
      if (finished) files.delete(item.id);
      return !finished;
    }));
  },
};
