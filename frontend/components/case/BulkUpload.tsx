"use client";

import { CheckCircle2, Clock3, Loader2, RotateCcw, UploadCloud, XCircle } from "lucide-react";
import { useEffect, useState, useSyncExternalStore, type DragEvent } from "react";
import { queueSummary, type EvidenceStatus } from "@/lib/evidence-queue";
import { evidenceStore } from "./evidence-store";

const STATUS_TEXT: Record<EvidenceStatus, string> = {
  queued: "Waiting",
  uploading: "Uploading",
  indexing: "Indexing",
  waiting: "Paused",
  done: "Ready",
  failed: "Failed",
};

function StatusIcon({ status }: { status: EvidenceStatus }) {
  if (status === "done") return <CheckCircle2 size={15} aria-hidden="true" />;
  if (status === "failed") return <XCircle size={15} aria-hidden="true" />;
  if (status === "uploading" || status === "indexing") return <Loader2 size={15} className="animate-spin" aria-hidden="true" />;
  return <Clock3 size={15} aria-hidden="true" />;
}

/** The drop area and a row per file, so one bad file is visibly one bad file. */
export default function BulkUpload({ caseId, docType, onIndexed }: { caseId: string; docType: string; onIndexed?: () => void }) {
  const all = useSyncExternalStore(evidenceStore.subscribe, evidenceStore.snapshot, evidenceStore.serverSnapshot);
  const items = all.filter((item) => item.caseId === caseId);
  const [dragging, setDragging] = useState(false);
  const summary = queueSummary(items);
  useEffect(() => { evidenceStore.setOnIndexed(onIndexed); }, [onIndexed]);

  const drop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    setDragging(false);
    evidenceStore.enqueue(Array.from(event.dataTransfer.files), caseId, docType);
  };
  return (
    <>
      <label
        className="evidence-drop"
        data-dragging={dragging || undefined}
        onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={drop}
      >
        <span className="evidence-drop-icon">
          {summary.active ? <Loader2 size={19} className="animate-spin" aria-hidden="true" /> : <UploadCloud size={19} aria-hidden="true" />}
        </span>
        <span className="evidence-drop-title">Choose or drop evidence to upload</span>
        <span className="evidence-drop-hint">PDF or TXT, up to 25 MiB each / stays inside this case</span>
        <input
          type="file"
          multiple
          accept="application/pdf,text/plain"
          className="sr-only"
          onChange={(event) => { const chosen = Array.from(event.target.files ?? []); event.target.value = ""; evidenceStore.enqueue(chosen, caseId, docType); }}
        />
      </label>
      {items.length > 0 && (
        <section className="evidence-queue" aria-label="Files being added">
          <div className="evidence-queue-head">
            <p role="status">
              {summary.finished} of {summary.total} finished{summary.failed ? `, ${summary.failed} failed` : ""}.
              {summary.active ? " Keep this page open until the rest are done." : ""}
            </p>
            {summary.finished > 0 && <button type="button" onClick={() => evidenceStore.clearFinished(caseId)}>Clear finished</button>}
          </div>
          <progress value={summary.finished} max={summary.total} aria-label="Files finished" />
          <ul>
            {items.map((item) => (
              <li key={item.id} data-status={item.status}>
                <span className="evidence-row-status"><StatusIcon status={item.status} />{STATUS_TEXT[item.status]}</span>
                <span className="evidence-row-name" title={item.name}>{item.name}</span>
                {item.detail && <span className="evidence-row-detail">{item.detail}</span>}
                {item.status === "failed" && item.retryable && (
                  <button type="button" onClick={() => evidenceStore.retry(item.id)} aria-label={`Retry ${item.name}`}>
                    <RotateCcw size={13} aria-hidden="true" />Retry
                  </button>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
