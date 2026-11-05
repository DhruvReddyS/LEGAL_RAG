/**
 * Many files going into one case, one at a time, through the existing upload
 * and index calls. One at a time because indexing reads, embeds and stores the
 * whole file on the server, and a failure here must never stop the next file.
 */

// The same ceiling and types the storage route enforces. Checked here too because
// a dropped file does not pass through the input's `accept`, and refusing it now
// saves sending 25 MiB only to hear no.
export const MAX_EVIDENCE_BYTES = 25 * 1024 * 1024;
export const EVIDENCE_TYPES = ["application/pdf", "text/plain"] as const;

// The index route allows only a few calls a minute per user, and a sliding window
// empties on its own, so a batch waits its turn rather than failing the fifth file.
export const RATE_LIMIT_WAIT_MS = 15_000;
export const RATE_LIMIT_ATTEMPTS = 8;

export type EvidenceStatus = "queued" | "uploading" | "indexing" | "waiting" | "done" | "failed";

export interface EvidenceItem {
  id: string;
  caseId: string;
  docType: string;
  name: string;
  status: EvidenceStatus;
  detail: string;
  /** Set once stored, so a retry indexes the same object instead of storing it twice. */
  objectId?: string;
  retryable: boolean;
}

export function evidenceRejection(file: { size: number; type: string }): string | null {
  if (file.size === 0) return "This file is empty.";
  if (file.size > MAX_EVIDENCE_BYTES) return "This file is larger than the 25 MiB limit.";
  if (!(EVIDENCE_TYPES as readonly string[]).includes(file.type.split(";")[0].trim().toLowerCase())) {
    return "Only PDF and TXT files can be added here.";
  }
  return null;
}

export interface EvidenceDeps {
  upload: () => Promise<{ id: string }>;
  index: (objectId: string) => Promise<{ pages: number; chunks: number }>;
  isRateLimited: (error: unknown) => boolean;
  errorText: (error: unknown) => string;
  wait: (ms: number) => Promise<void>;
  onChange: (change: Partial<EvidenceItem>) => void;
}

/** Settles for every file: a failure is reported on that row and never thrown. */
export async function processEvidenceItem(item: Pick<EvidenceItem, "objectId">, deps: EvidenceDeps): Promise<boolean> {
  let objectId = item.objectId;
  try {
    if (!objectId) {
      deps.onChange({ status: "uploading", detail: "" });
      objectId = (await deps.upload()).id;
      deps.onChange({ objectId });
    }
    for (let attempt = 1; ; attempt += 1) {
      deps.onChange({ status: "indexing", detail: "" });
      try {
        const indexed = await deps.index(objectId);
        deps.onChange({ status: "done", detail: `${indexed.pages} page(s), ${indexed.chunks} private passage(s).`, retryable: false });
        return true;
      } catch (error) {
        if (!deps.isRateLimited(error) || attempt >= RATE_LIMIT_ATTEMPTS) throw error;
        deps.onChange({ status: "waiting", detail: "The server allows only a few of these a minute. It will continue shortly." });
        await deps.wait(RATE_LIMIT_WAIT_MS);
      }
    }
  } catch (error) {
    const stored = objectId ? "Stored, but not indexed. " : "";
    deps.onChange({ status: "failed", detail: `${stored}${deps.errorText(error)}`, retryable: true });
    return false;
  }
}

export function queueSummary(items: Pick<EvidenceItem, "status">[]): { finished: number; total: number; failed: number; active: boolean } {
  const failed = items.filter((item) => item.status === "failed").length;
  const finished = failed + items.filter((item) => item.status === "done").length;
  return { finished, total: items.length, failed, active: finished < items.length };
}
