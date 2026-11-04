"use client";

import { ExternalLink, Loader2, LockKeyhole, Route, ShieldAlert, ShieldCheck, ThumbsDown, ThumbsUp } from "lucide-react";
import { useEffect, useState } from "react";
import { formatCount, formatPercent, formatWhen, toQuery } from "@/lib/admin-presentation";
import {
  listFeedback,
  listQuarantines,
  previewQuarantine,
  quarantineDocument,
  releaseQuarantine,
  traceFeedback,
  updateTriage,
} from "@/lib/api-admin";
import type { FeedbackTrace, QuarantinePreview, TriageStatus } from "@/lib/types-admin";
import { ConfirmDialog, Dialog, LoadState, messageOf, Notice, PanelHeading, Pager, StatusPill, useLoaded } from "./shared";

const PAGE_SIZE = 20;
const STATUSES: Record<TriageStatus, string> = { open: "Open", investigating: "Investigating", resolved: "Resolved", dismissed: "Dismissed" };

export default function IncidentsPanel({ prefillDocument, onPrefillUsed }: { prefillDocument: string | null; onPrefillUsed: () => void }) {
  const [rating, setRating] = useState<"up" | "down" | "">("down");
  const [status, setStatus] = useState<TriageStatus | "">("open");
  const [page, setPage] = useState(1);
  const [tracing, setTracing] = useState<string | null>(null);
  const [quarantineTarget, setQuarantineTarget] = useState<{ documentId: string; feedbackId: string | null } | null>(null);
  const [quarantineNonce, setQuarantineNonce] = useState(0);

  const filters = { rating, status, page, page_size: PAGE_SIZE };
  const { data, error, loading, reload } = useLoaded(() => listFeedback(filters), toQuery(filters));

  useEffect(() => {
    if (prefillDocument) {
      setQuarantineTarget({ documentId: prefillDocument, feedbackId: null });
      onPrefillUsed();
    }
  }, [prefillDocument, onPrefillUsed]);

  return (
    <div className="admin-stack">
      <section className="admin-panel">
        <PanelHeading title="Feedback to triage" description="Ratings only. Conversation text appears when you trace an answer, and that trace is recorded." />
        <div className="admin-filters">
          <label className="admin-inline-field">
            <span>Rating</span>
            <select className="field" value={rating} onChange={event => { setRating(event.target.value as typeof rating); setPage(1); }}>
              <option value="">Any</option>
              <option value="down">Not helpful</option>
              <option value="up">Helpful</option>
            </select>
          </label>
          <label className="admin-inline-field">
            <span>Status</span>
            <select className="field" value={status} onChange={event => { setStatus(event.target.value as TriageStatus | ""); setPage(1); }}>
              <option value="">Any</option>
              {(Object.keys(STATUSES) as TriageStatus[]).map(name => <option key={name} value={name}>{STATUSES[name]}</option>)}
            </select>
          </label>
        </div>
        <LoadState loading={loading && !data} error={error} onRetry={reload} empty={data && data.items.length === 0 ? "Nothing here matches. Clear the filters to see everything." : null} />
        {data && data.items.length > 0 && (
          <>
            <ul className="admin-list">
              {data.items.map(item => (
                <li key={item.id}>
                  <div className="admin-doc-head">
                    <div className="admin-row">
                      {item.rating === "down" ? <ThumbsDown size={14} aria-label="Not helpful" /> : <ThumbsUp size={14} aria-label="Helpful" />}
                      <strong>{formatWhen(item.answered_at)}</strong>
                      <span className="admin-muted">{item.role}</span>
                    </div>
                    <div className="admin-row">
                      <StatusPill tone={item.status === "open" ? "warn" : item.status === "investigating" ? "warn" : item.status === "resolved" ? "ok" : "neutral"}>{STATUSES[item.status]}</StatusPill>
                      {item.case_linked && <StatusPill tone="neutral">Case-linked</StatusPill>}
                    </div>
                  </div>
                  <small className="admin-muted">
                    {item.citation_count} citations / confidence {formatPercent(item.confidence_score)}{item.has_correction ? " / correction supplied" : ""}
                  </small>
                  <div className="admin-actions">
                    <button className="button-secondary admin-compact" onClick={() => setTracing(item.id)}>
                      <Route size={13} aria-hidden="true" /> Trace to chunks
                    </button>
                  </div>
                </li>
              ))}
            </ul>
            <Pager page={page} pageSize={PAGE_SIZE} total={data.total} onPage={setPage} noun="ratings" />
          </>
        )}
      </section>

      <QuarantineSection
        key={quarantineNonce}
        onStart={documentId => setQuarantineTarget({ documentId, feedbackId: null })}
      />

      {tracing && (
        <TraceDialog
          feedbackId={tracing}
          onClose={() => { setTracing(null); reload(); }}
          onQuarantine={documentId => setQuarantineTarget({ documentId, feedbackId: tracing })}
        />
      )}
      {quarantineTarget && (
        <QuarantineDialog
          target={quarantineTarget}
          onClose={() => setQuarantineTarget(null)}
          onDone={() => setQuarantineNonce(value => value + 1)}
        />
      )}
    </div>
  );
}

function TraceDialog({ feedbackId, onClose, onQuarantine }: { feedbackId: string; onClose: () => void; onQuarantine: (documentId: string) => void }) {
  const [trace, setTrace] = useState<FeedbackTrace | null>(null);
  const [error, setError] = useState("");
  const [status, setStatus] = useState<TriageStatus>("open");
  const [note, setNote] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let active = true;
    traceFeedback(feedbackId)
      .then(result => {
        if (!active) return;
        setTrace(result);
        setStatus(result.status);
        setNote(result.note ?? "");
      })
      .catch(cause => { if (active) setError(messageOf(cause, "This answer could not be traced.")); });
    return () => { active = false; };
  }, [feedbackId]);

  return (
    <Dialog title="Trace this answer" onClose={onClose} wide>
      <LoadState loading={!trace && !error} error={error} />
      {trace && (
        <div className="admin-stack is-tight">
          <p className="admin-footnote">This view has been recorded in the audit log. Nothing the user wrote was copied into that record.</p>
          {trace.case_linked ? (
            <Notice>
              <LockKeyhole size={14} aria-hidden="true" />
              <span>
                This answer belongs to a private matter, so the answer and any correction are withheld. A rating is not an authorised matter.
                {trace.citations_withheld > 0 && ` ${trace.citations_withheld} citation${trace.citations_withheld === 1 ? "" : "s"} not proved to come from the global corpus ${trace.citations_withheld === 1 ? "is" : "are"} withheld too.`}
                {!trace.corpus_checked && " The corpus could not be reached to check them, so nothing is shown."}
              </span>
            </Notice>
          ) : (
            <>
              {trace.correction && (
                <div>
                  <h4 className="admin-subhead">Correction the user supplied</h4>
                  <blockquote className="admin-quote">{trace.correction}</blockquote>
                </div>
              )}
              {trace.answer && (
                <details className="admin-details" open>
                  <summary>The answer</summary>
                  <div className="admin-quote is-scroll">{trace.answer}</div>
                </details>
              )}
              {!trace.corpus_checked && <Notice tone="warn">The corpus could not be reached, so sources could not be matched to documents.</Notice>}
            </>
          )}
          <div>
            <h4 className="admin-subhead">Sources it cited</h4>
            {trace.citations.length ? (
              <ul className="admin-list">
                {trace.citations.map(citation => (
                  <li key={citation.chunk_id}>
                    <div className="admin-doc-head">
                      <strong>{citation.number ? `[${citation.number}] ` : ""}{citation.title ?? citation.chunk_id}</strong>
                      <div className="admin-row">
                        {citation.current_status && <StatusPill tone={citation.current_status === "current" ? "ok" : citation.current_status === "status_unverified" || citation.current_status === "not_applicable" ? "warn" : "bad"}>{citation.current_status.replace(/_/g, " ")}</StatusPill>}
                        {citation.quarantined && <StatusPill tone="bad">Quarantined</StatusPill>}
                      </div>
                    </div>
                    <small className="admin-muted admin-wrap">
                      {[citation.act_name, citation.section ? `s.${citation.section}` : null, citation.page_start ? `pp. ${citation.page_start} to ${citation.page_end}` : null, citation.verification_status, citation.corpus_tier].filter(Boolean).join(" / ")}
                    </small>
                    {citation.excerpt && <blockquote className="admin-quote">{citation.excerpt}</blockquote>}
                    <div className="admin-row admin-doc-actions">
                      {citation.source_url && <a className="admin-link" href={citation.source_url} target="_blank" rel="noreferrer">Official source <ExternalLink size={11} aria-hidden="true" /></a>}
                      {citation.canonical_document_id && !citation.quarantined && (
                        <button className="admin-link" onClick={() => onQuarantine(citation.canonical_document_id as string)}>
                          <ShieldAlert size={11} aria-hidden="true" /> Quarantine this document
                        </button>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="admin-empty">No sources to show.</p>
            )}
          </div>
          <div className="admin-form">
            <h4 className="admin-subhead">Triage</h4>
            <div className="admin-form-pair">
              <label className="admin-field">
                <span>Status</span>
                <select className="field" value={status} onChange={event => { setStatus(event.target.value as TriageStatus); setSaved(false); }}>
                  {(Object.keys(STATUSES) as TriageStatus[]).map(name => <option key={name} value={name}>{STATUSES[name]}</option>)}
                </select>
              </label>
              <label className="admin-field">
                <span>Your note</span>
                <input className="field" value={note} maxLength={1000} onChange={event => { setNote(event.target.value); setSaved(false); }} />
              </label>
            </div>
            <div className="admin-actions">
              <button
                className="button-primary"
                onClick={async () => {
                  setError("");
                  try { await updateTriage(feedbackId, status, note.trim() || null); setSaved(true); }
                  catch (cause) { setError(messageOf(cause, "That was not saved.")); }
                }}
              >
                Save triage
              </button>
              {saved && <span role="status" className="admin-muted">Saved.</span>}
            </div>
          </div>
        </div>
      )}
    </Dialog>
  );
}

function QuarantineDialog({ target, onClose, onDone }: { target: { documentId: string; feedbackId: string | null }; onClose: () => void; onDone: () => void }) {
  const [preview, setPreview] = useState<QuarantinePreview | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    previewQuarantine(target.documentId)
      .then(result => { if (active) setPreview(result); })
      .catch(cause => { if (active) setError(messageOf(cause, "Could not preview this document.")); });
    return () => { active = false; };
  }, [target.documentId]);

  if (error) {
    return <Dialog title="Quarantine a document" onClose={onClose}><Notice tone="bad">{error}</Notice></Dialog>;
  }
  if (!preview) {
    return <Dialog title="Quarantine a document" onClose={onClose}><LoadState loading error="" /></Dialog>;
  }
  if (preview.already_quarantined) {
    return <Dialog title="Quarantine a document" onClose={onClose}><Notice>This document is already quarantined.</Notice></Dialog>;
  }
  return (
    <ConfirmDialog
      title="Quarantine this document"
      confirmLabel="Withhold from retrieval"
      danger
      requireReason
      reasonLabel="Why it is being withheld"
      typed={preview.canonical_document_id}
      body={
        <div className="admin-stack is-tight">
          <p><strong>{preview.title ?? "This document is not in the current manifest."}</strong></p>
          <dl className="admin-defs">
            <div><dt>Document</dt><dd><code>{preview.canonical_document_id}</code></dd></div>
            <div><dt>Passages withheld</dt><dd>{preview.points_in_serving_collection === null ? "Could not count" : formatCount(preview.points_in_serving_collection)} in <code>{preview.serving_collection}</code></dd></div>
            {preview.corpus_tier && <div><dt>Tier</dt><dd>{preview.corpus_tier}</dd></div>}
            {preview.current_status && <div><dt>Recorded status</dt><dd>{preview.current_status}</dd></div>}
          </dl>
          <p>From the next query, Fast, Deep, drafting and analysis all stop retrieving it, and its sources stop opening. Past answers stay as they were. Nothing is deleted, and it can be released.</p>
        </div>
      }
      onClose={onClose}
      onConfirm={async reason => {
        await quarantineDocument({ canonical_document_id: preview.canonical_document_id, reason, feedback_id: target.feedbackId });
        onDone();
      }}
    />
  );
}

function QuarantineSection({ onStart }: { onStart: (documentId: string) => void }) {
  const [includeReleased, setIncludeReleased] = useState(false);
  const [documentId, setDocumentId] = useState("");
  const [releasing, setReleasing] = useState<string | null>(null);
  const { data, error, loading, reload } = useLoaded(() => listQuarantines(includeReleased), String(includeReleased));

  return (
    <section className="admin-panel">
      <PanelHeading
        title="Quarantined documents"
        description="Withheld from every path into the global corpus. Case documents are never affected."
        actions={
          <label className="admin-check">
            <input type="checkbox" checked={includeReleased} onChange={event => setIncludeReleased(event.target.checked)} />
            <span>Show released</span>
          </label>
        }
      />
      <form
        className="admin-form admin-form-row"
        onSubmit={event => { event.preventDefault(); if (documentId.trim()) onStart(documentId.trim()); }}
      >
        <label className="admin-field">
          <span>Document id</span>
          <input className="field" value={documentId} placeholder="From the corpus browser or a trace" onChange={event => setDocumentId(event.target.value)} />
        </label>
        <button className="button-secondary" disabled={!documentId.trim()}>
          <ShieldAlert size={14} aria-hidden="true" /> Preview quarantine
        </button>
      </form>
      <LoadState loading={loading && !data} error={error} onRetry={reload} empty={data && data.quarantines.length === 0 ? "Nothing is quarantined." : null} />
      {data && data.quarantines.length > 0 && (
        <ul className="admin-list">
          {data.quarantines.map(row => (
            <li key={row.id}>
              <div className="admin-doc-head">
                <strong>{row.title ?? row.canonical_document_id}</strong>
                <StatusPill tone={row.released_at ? "neutral" : "bad"}>{row.released_at ? "Released" : "Quarantined"}</StatusPill>
              </div>
              <small className="admin-muted admin-wrap"><code>{row.canonical_document_id}</code> since {formatWhen(row.quarantined_at)}</small>
              <p>{row.reason}</p>
              {row.released_at && <small className="admin-muted">Released {formatWhen(row.released_at)}: {row.release_reason}</small>}
              {!row.released_at && (
                <div className="admin-actions">
                  <button className="button-secondary admin-compact" onClick={() => setReleasing(row.id)}>
                    <ShieldCheck size={13} aria-hidden="true" /> Release
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      {releasing && (
        <ConfirmDialog
          title="Release this document"
          confirmLabel="Return to retrieval"
          requireReason
          reasonLabel="Why it can return"
          body={<p>It becomes retrievable again from the next query.</p>}
          onClose={() => setReleasing(null)}
          onConfirm={async reason => { await releaseQuarantine(releasing, reason); reload(); }}
        />
      )}
      {loading && data && <Loader2 size={12} className="animate-spin admin-muted" aria-hidden="true" />}
    </section>
  );
}
