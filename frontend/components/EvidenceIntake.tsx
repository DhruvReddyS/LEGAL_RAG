"use client";

import { CheckCircle2, Clock3, Loader2, RotateCcw, UploadCloud, XCircle } from "lucide-react";
import { useState, type DragEvent } from "react";
import { queueSummary, type EvidenceItem, type EvidenceStatus } from "@/lib/evidence-queue";

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
export default function EvidenceIntake({ items, onFiles, onRetry, onClear }: {
  items: EvidenceItem[];
  onFiles: (files: File[]) => void;
  onRetry: (id: string) => void;
  onClear: () => void;
}) {
  const [dragging, setDragging] = useState(false);
  const summary = queueSummary(items);
  const drop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    setDragging(false);
    onFiles(Array.from(event.dataTransfer.files));
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
          onChange={(event) => { const chosen = Array.from(event.target.files ?? []); event.target.value = ""; onFiles(chosen); }}
        />
      </label>
      {items.length > 0 && (
        <section className="evidence-queue" aria-label="Files being added">
          <div className="evidence-queue-head">
            <p role="status">
              {summary.finished} of {summary.total} finished{summary.failed ? `, ${summary.failed} failed` : ""}.
              {summary.active ? " Keep this workspace open until the rest are done." : ""}
            </p>
            {summary.finished > 0 && <button type="button" onClick={onClear}>Clear finished</button>}
          </div>
          <progress value={summary.finished} max={summary.total} aria-label="Files finished" />
          <ul>
            {items.map((item) => (
              <li key={item.id} data-status={item.status}>
                <span className="evidence-row-status"><StatusIcon status={item.status} />{STATUS_TEXT[item.status]}</span>
                <span className="evidence-row-name" title={item.name}>{item.name}</span>
                {item.detail && <span className="evidence-row-detail">{item.detail}</span>}
                {item.status === "failed" && item.retryable && (
                  <button type="button" onClick={() => onRetry(item.id)} aria-label={`Retry ${item.name}`}>
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
