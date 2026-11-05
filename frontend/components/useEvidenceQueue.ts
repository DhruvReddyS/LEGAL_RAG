"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, indexCaseEvidence, uploadCaseEvidence } from "@/lib/api";
import { evidenceRejection, processEvidenceItem, type EvidenceItem } from "@/lib/evidence-queue";

function errorText(error: unknown): string {
  return error instanceof ApiError ? error.message : "The operation failed. Check the connection and try again.";
}

/**
 * Lives in the workspace rather than the intake view, so moving to another tool
 * or case does not lose the batch. Each row keeps the case it was added to.
 */
export function useEvidenceQueue(onIndexed: () => void) {
  const [items, setItems] = useState<EvidenceItem[]>([]);
  const list = useRef<EvidenceItem[]>([]);
  const files = useRef(new Map<string, File>());
  const draining = useRef(false);
  const alive = useRef(true);
  const nextId = useRef(0);
  const notify = useRef(onIndexed);
  notify.current = onIndexed;

  const commit = useCallback((next: EvidenceItem[]) => {
    list.current = next;
    setItems(next);
  }, []);
  const patch = useCallback((id: string, change: Partial<EvidenceItem>) => {
    commit(list.current.map((item) => (item.id === id ? { ...item, ...change } : item)));
  }, [commit]);

  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);

  const drain = useCallback(async () => {
    if (draining.current) return;
    draining.current = true;
    try {
      for (;;) {
        const item = list.current.find((row) => row.status === "queued");
        if (!item || !alive.current) return;
        const file = files.current.get(item.id);
        if (!file) { patch(item.id, { status: "failed", detail: "This file is no longer available. Choose it again.", retryable: false }); continue; }
        const done = await processEvidenceItem(item, {
          upload: () => uploadCaseEvidence(item.caseId, file),
          index: (objectId) => indexCaseEvidence(item.caseId, objectId, item.docType),
          isRateLimited: (error) => error instanceof ApiError && error.status === 429,
          errorText,
          wait: (ms) => new Promise((resolve) => window.setTimeout(resolve, ms)),
          onChange: (change) => patch(item.id, change),
        });
        if (done) { files.current.delete(item.id); if (alive.current) notify.current(); }
      }
    } finally {
      draining.current = false;
    }
  }, [patch]);

  const enqueue = useCallback((chosen: File[], caseId: string, docType: string) => {
    if (!chosen.length || !caseId) return;
    const added = chosen.map((file): EvidenceItem => {
      nextId.current += 1;
      const id = `evidence-${nextId.current}`;
      const rejection = evidenceRejection(file);
      if (!rejection) files.current.set(id, file);
      return {
        id, caseId, docType, name: file.name,
        status: rejection ? "failed" : "queued",
        detail: rejection ?? "",
        retryable: false,
      };
    });
    commit([...list.current, ...added]);
    void drain();
  }, [commit, drain]);

  const retry = useCallback((id: string) => {
    patch(id, { status: "queued", detail: "", retryable: false });
    void drain();
  }, [patch, drain]);

  const clearFinished = useCallback((caseId: string) => {
    commit(list.current.filter((item) => {
      const finished = item.status === "done" || item.status === "failed";
      if (finished && item.caseId === caseId) files.current.delete(item.id);
      return !(finished && item.caseId === caseId);
    }));
  }, [commit]);

  return { items, enqueue, retry, clearFinished };
}
