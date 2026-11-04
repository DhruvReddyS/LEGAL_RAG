"use client";

import { ExternalLink, FileUp, FileCheck2, Loader2, Search, ShieldAlert } from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { listCorpusIntakes, publishCorpusIntake, stageCorpusIntake, validateCorpusIntake } from "@/lib/api";
import { currencyLabel, currencyTone, formatCount, toQuery } from "@/lib/admin-presentation";
import { browseCorpus, setWorkItem } from "@/lib/api-admin";
import type { CorpusIntake } from "@/lib/types";
import type { CorpusDocument, WorkQueue, WorkStatus } from "@/lib/types-admin";
import { LoadState, messageOf, Notice, PanelHeading, Pager, Stat, StatusPill, useLoaded } from "./shared";

const PAGE_SIZE = 25;
const QUEUE_LABELS: Record<WorkQueue, string> = { ocr: "OCR", verification: "Verification", currency: "Currency" };
const WORK_LABELS: Record<WorkStatus, string> = { open: "Open", in_progress: "In progress", done: "Done" };

export default function CorpusPanel({ onQuarantine }: { onQuarantine: (documentId: string) => void }) {
  const [input, setInput] = useState("");
  const [q, setQ] = useState("");
  const [sourceType, setSourceType] = useState("");
  const [domain, setDomain] = useState("");
  const [currency, setCurrency] = useState("");
  const [queue, setQueue] = useState<WorkQueue | "">("");
  const [workStatus, setWorkStatus] = useState<WorkStatus | "">("");
  const [page, setPage] = useState(1);

  useEffect(() => {
    const timer = window.setTimeout(() => { setQ(input.trim()); setPage(1); }, 250);
    return () => window.clearTimeout(timer);
  }, [input]);

  const filters = { q, source_type: sourceType, domain, currency, queue, work_status: queue ? workStatus : "", page, page_size: PAGE_SIZE };
  const { data, error, loading, reload } = useLoaded(() => browseCorpus(filters), toQuery(filters));
  const reset = (setter: (value: string) => void) => (value: string) => { setter(value); setPage(1); };

  return (
    <div className="admin-stack">
      <section className="admin-panel">
        <PanelHeading title="Corpus coverage" description="What the manifest says the corpus holds. Public law only: private case material never appears here." />
        {data && (
          <div className="admin-stats">
            <Stat label="Documents" value={formatCount(data.total_documents)} />
            <Stat label="Pages" value={formatCount(data.total_pages)} />
            <Stat label="Repealed or superseded" value={formatCount(data.facets.currency.repealed_or_superseded ?? 0)} />
            <Stat label="Quarantined" value={formatCount(data.quarantined)} />
          </div>
        )}
        <div className="admin-queues" role="group" aria-label="Work lists">
          <button aria-pressed={queue === ""} onClick={() => { setQueue(""); setWorkStatus(""); setPage(1); }}>All documents</button>
          {(Object.keys(QUEUE_LABELS) as WorkQueue[]).map(name => (
            <button key={name} aria-pressed={queue === name} onClick={() => { setQueue(name); setPage(1); }}>
              {QUEUE_LABELS[name]} queue <b>{data ? formatCount(data.facets.queue[name]) : ""}</b>
            </button>
          ))}
        </div>
        <div className="admin-filters">
          <label className="admin-search">
            <Search size={15} aria-hidden="true" />
            <span className="sr-only">Search the corpus</span>
            <input value={input} placeholder="Title, Act, category or document id" onChange={event => setInput(event.target.value)} />
          </label>
          <FacetSelect label="Type" value={sourceType} options={data?.facets.source_type} onChange={reset(setSourceType)} />
          <FacetSelect label="Domain" value={domain} options={data?.facets.domain} onChange={reset(setDomain)} />
          <FacetSelect label="Currency" value={currency} options={data?.facets.currency} labelFor={currencyLabel} onChange={reset(setCurrency)} />
          {queue && (
            <label className="admin-inline-field">
              <span>Progress</span>
              <select className="field" value={workStatus} onChange={event => { setWorkStatus(event.target.value as WorkStatus | ""); setPage(1); }}>
                <option value="">Any</option>
                {(Object.keys(WORK_LABELS) as WorkStatus[]).map(name => <option key={name} value={name}>{WORK_LABELS[name]}</option>)}
              </select>
            </label>
          )}
        </div>
        <LoadState
          loading={loading && !data}
          error={error}
          onRetry={reload}
          empty={data && data.total_documents === 0 ? "No manifest was found at the configured knowledge-base path." : data && data.total === 0 ? "No documents match these filters." : null}
        />
        {data && data.documents.length > 0 && (
          <>
            <ul className="admin-list">
              {data.documents.map(document => (
                <DocumentRow key={document.canonical_document_id} document={document} queue={queue} onChanged={reload} onQuarantine={onQuarantine} />
              ))}
            </ul>
            <Pager page={page} pageSize={PAGE_SIZE} total={data.total} onPage={setPage} noun="documents" />
          </>
        )}
      </section>
      <IntakeSection />
    </div>
  );
}

function FacetSelect({ label, value, options, labelFor, onChange }: { label: string; value: string; options?: Record<string, number>; labelFor?: (key: string) => string; onChange: (value: string) => void }) {
  return (
    <label className="admin-inline-field">
      <span>{label}</span>
      <select className="field" value={value} onChange={event => onChange(event.target.value)}>
        <option value="">All</option>
        {Object.entries(options ?? {}).map(([key, count]) => (
          <option key={key} value={key}>{labelFor ? labelFor(key) : key} ({count})</option>
        ))}
      </select>
    </label>
  );
}

function DocumentRow({ document, queue, onChanged, onQuarantine }: { document: CorpusDocument; queue: WorkQueue | ""; onChanged: () => void; onQuarantine: (id: string) => void }) {
  const [note, setNote] = useState(document.work_note ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const save = async (status: WorkStatus) => {
    if (!queue) return;
    setBusy(true);
    setError("");
    try {
      await setWorkItem({ canonical_document_id: document.canonical_document_id, queue, status, note: note.trim() || null });
      onChanged();
    } catch (cause) { setError(messageOf(cause, "That was not saved.")); }
    finally { setBusy(false); }
  };
  return (
    <li>
      <div className="admin-doc-head">
        <strong>{document.title}</strong>
        <div className="admin-row">
          <StatusPill tone={currencyTone(document.currency_flag)}>{currencyLabel(document.currency_flag)}</StatusPill>
          {document.ocr_required && <StatusPill tone="warn">Needs OCR</StatusPill>}
          {!document.verified_official && <StatusPill tone="warn">Not verified official</StatusPill>}
          {document.quarantined && <StatusPill tone="bad">Quarantined</StatusPill>}
        </div>
      </div>
      <small className="admin-muted admin-wrap">
        {document.source_type} / {document.category} / {document.page_count} pages / recorded status: {document.current_status}
      </small>
      {document.superseded_by && <p className="admin-note">Replaced by {document.superseded_by}</p>}
      {document.currency_note && <p className="admin-note">{document.currency_note}</p>}
      <div className="admin-row admin-doc-actions">
        {document.source_url && (
          <a className="admin-link" href={document.source_url} target="_blank" rel="noreferrer">
            Official source <ExternalLink size={11} aria-hidden="true" />
          </a>
        )}
        {!document.quarantined && (
          <button className="admin-link" onClick={() => onQuarantine(document.canonical_document_id)}>
            <ShieldAlert size={11} aria-hidden="true" /> Quarantine
          </button>
        )}
      </div>
      {queue && (
        <div className="admin-work">
          <label className="admin-inline-field">
            <span>{QUEUE_LABELS[queue]} progress</span>
            <select
              className="field"
              value={document.work_status}
              disabled={busy}
              onChange={event => save(event.target.value as WorkStatus)}
            >
              {(Object.keys(WORK_LABELS) as WorkStatus[]).map(name => <option key={name} value={name}>{WORK_LABELS[name]}</option>)}
            </select>
          </label>
          <label className="admin-inline-field is-grow">
            <span>Note</span>
            <input
              className="field"
              value={note}
              maxLength={1000}
              onChange={event => setNote(event.target.value)}
              onBlur={() => { if (note.trim() !== (document.work_note ?? "")) void save(document.work_status); }}
            />
          </label>
          {error && <Notice tone="bad">{error}</Notice>}
        </div>
      )}
    </li>
  );
}

function formatBytes(value: number) {
  return value < 1024 * 1024 ? `${Math.round(value / 1024)} KB` : `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function IntakeSection() {
  const [intakes, setIntakes] = useState<CorpusIntake[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const refresh = useCallback(async () => {
    const result = await listCorpusIntakes();
    setIntakes(result.intakes);
  }, []);
  useEffect(() => {
    refresh().catch(cause => setNotice(messageOf(cause, "Unable to load the intake queue")));
  }, [refresh]);

  const stage = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const element = event.currentTarget;
    const form = new FormData(element);
    const file = form.get("file");
    setNotice("");
    if (!(file instanceof File) || !file.size) { setNotice("Choose a PDF to stage."); return; }
    setBusy("stage");
    try {
      await stageCorpusIntake({ file, title: String(form.get("title")), sourceType: String(form.get("sourceType")), jurisdiction: String(form.get("jurisdiction")), authority: String(form.get("authority") ?? ""), sourceUrl: String(form.get("sourceUrl")) });
      element.reset();
      setNotice("Document staged. Run validation before publishing.");
      await refresh();
    } catch (cause) { setNotice(messageOf(cause, "Corpus intake failed")); }
    finally { setBusy(null); }
  };

  const advance = async (intake: CorpusIntake) => {
    setBusy(intake.id);
    setNotice("");
    try {
      if (intake.status === "validated") {
        const result = await publishCorpusIntake(intake.id);
        setNotice(`Published ${result.indexed_chunks} verified extended-corpus passages.`);
      } else {
        const result = await validateCorpusIntake(intake.id);
        setNotice(result.status === "validated" ? "Quality validation passed. The source is ready for publication." : "The source failed extraction quality checks.");
      }
      await refresh();
    } catch (cause) { setNotice(messageOf(cause, "Corpus operation failed")); }
    finally { setBusy(null); }
  };

  return (
    <section className="admin-panel">
      <PanelHeading title="Add to the corpus" description="Stage an official PDF, validate it, then publish to the verified extended tier. Gold stays immutable." />
      {notice && <Notice>{notice}</Notice>}
      <div className="admin-two">
        <form className="admin-form" onSubmit={stage}>
          <label className="admin-field"><span>Official source title</span><input required name="title" className="field" /></label>
          <div className="admin-form-pair">
            <label className="admin-field"><span>Type</span><select name="sourceType" className="field"><option value="act">Act or statute</option><option value="judgment">Judgment</option><option value="notification">Notification</option></select></label>
            <label className="admin-field"><span>Jurisdiction</span><input required name="jurisdiction" defaultValue="India" className="field" /></label>
          </div>
          <label className="admin-field"><span>Court or issuing authority</span><input name="authority" className="field" /></label>
          <label className="admin-field"><span>Official source URL</span><input required name="sourceUrl" type="url" placeholder="https://" className="field" /></label>
          <label className="admin-field"><span>PDF, up to 30 MiB</span><input required name="file" type="file" accept="application/pdf" className="field" /></label>
          <button disabled={busy === "stage"} className="button-primary">
            {busy === "stage" ? <Loader2 size={14} className="animate-spin" aria-hidden="true" /> : <FileUp size={14} aria-hidden="true" />} Stage for validation
          </button>
        </form>
        <div>
          <h4 className="admin-subhead">Intake queue</h4>
          {intakes.length ? (
            <ul className="admin-list">
              {intakes.map(intake => (
                <li key={intake.id}>
                  <div className="admin-doc-head">
                    <strong>{intake.title}</strong>
                    <StatusPill tone={intake.status === "published" ? "ok" : intake.status === "rejected" ? "bad" : "warn"}>{intake.status}</StatusPill>
                  </div>
                  <small className="admin-muted admin-wrap">{intake.filename} / {formatBytes(intake.file_size)} / {intake.source_type}</small>
                  {intake.status !== "published" && (
                    <div className="admin-actions">
                      <button className="button-secondary admin-compact" disabled={busy === intake.id} onClick={() => advance(intake)}>
                        {busy === intake.id ? <Loader2 size={13} className="animate-spin" aria-hidden="true" /> : <FileCheck2 size={13} aria-hidden="true" />}
                        {intake.status === "validated" ? "Publish to extended" : "Run validation"}
                      </button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className="admin-empty">No corpus additions staged.</p>
          )}
        </div>
      </div>
    </section>
  );
}
