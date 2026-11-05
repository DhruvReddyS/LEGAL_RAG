"use client";

import { Check, ClipboardCopy, Download, FileSearch, FileText, Loader2, Scale, UploadCloud } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { DefenceAnalysisResult } from "@/components/advocate/DefenceAnalysisResult";
import { ApiError, analyseDefence, draftFir, indexCaseEvidence, listGeneratedDocuments, listIndexedCaseDocuments, readGeneratedDocument, scopedSearch, uploadCaseEvidence } from "@/lib/api";
import { plural, shortDate } from "@/lib/pro-presentation";
import type { CaseDocumentSummary, DefenceAnalysisResponse, FIRDraftResponse, GeneratedDocumentSummary, RetrievalHit } from "@/lib/types";
import { CaseBulkUpload } from "./slots";

/**
 * The case tools that used to live inside ProfessionalWorkspace, each now on its own.
 * Behaviour is the same; only the selected-case state is gone, because each of these
 * is mounted under the case it belongs to.
 */
const errorText = (error: unknown) => (error instanceof ApiError ? error.message : "The operation failed. Check the connection and try again.");

function Notice({ text, failed }: { text: string; failed: boolean }) {
  if (!text) return null;
  return <p className={`pro-notice ${failed ? "is-bad" : ""}`} role={failed ? "alert" : "status"}>{text}</p>;
}

const docLabel = (type: string) => type.split(/[_-]/).map((word) => (word.toUpperCase() === "FIR" ? "FIR" : word)).join(" ").replace(/^./, (c) => c.toUpperCase());

/** Police: a reviewable FIR draft from the known facts, with the versions kept so far. */
export function FirDraftPanel({ caseId, caseTitle, onChanged }: { caseId: string; caseTitle: string; onChanged: () => void }) {
  const [scenario, setScenario] = useState("");
  const [draft, setDraft] = useState<FIRDraftResponse | null>(null);
  const [drafts, setDrafts] = useState<GeneratedDocumentSummary[] | null>(null);
  const [listFailed, setListFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState({ text: "", failed: false });
  const [copied, setCopied] = useState(false);
  const refresh = useCallback(() => {
    setListFailed(false);
    listGeneratedDocuments(caseId).then((response) => setDrafts(response.documents)).catch(() => { setDrafts(null); setListFailed(true); });
  }, [caseId]);
  useEffect(refresh, [refresh]);
  const generate = async () => {
    setBusy(true); setNotice({ text: "", failed: false }); setDraft(null);
    try {
      const result = await draftFir(caseId, scenario.trim());
      setDraft(result);
      setNotice({ text: `Created draft version ${result.version}. It stays a draft until you review it.`, failed: false });
      refresh(); onChanged();
    } catch (error) { setNotice({ text: errorText(error), failed: true }); } finally { setBusy(false); }
  };
  const open = async (id: string) => {
    setBusy(true); setNotice({ text: "", failed: false });
    // Read back, never re-drafted: a reviewed draft must not change under the officer who reviewed it.
    try { setDraft(await readGeneratedDocument(caseId, id)); }
    catch (error) { setNotice({ text: errorText(error), failed: true }); } finally { setBusy(false); }
  };
  // The disclaimer travels with the text. A draft pasted without it reads as finished.
  const fullText = (item: FIRDraftResponse) => `${item.rendered_text}\n\n---\n${item.disclaimer}`;
  const copy = async (item: FIRDraftResponse) => {
    try { await navigator.clipboard.writeText(fullText(item)); setCopied(true); window.setTimeout(() => setCopied(false), 2000); }
    catch { setNotice({ text: "The browser refused clipboard access. Select the text and copy it instead.", failed: true }); }
  };
  const save = (item: FIRDraftResponse) => {
    const url = URL.createObjectURL(new Blob([fullText(item)], { type: "text/plain;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `${item.doc_type}-v${item.version}-${caseTitle.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}.txt`;
    link.click();
    URL.revokeObjectURL(url);
  };
  return (
    <div className="pro-stack">
      <label className="pro-label">What is known so far
        <textarea className="field min-h-44 resize-y leading-6" value={scenario} placeholder="The complainant's account, dates, location, property or person description, witnesses and known circumstances." onChange={(event) => setScenario(event.target.value)} />
        <small>At least 40 characters. Anything you leave out stays visibly incomplete in the draft.</small>
      </label>
      <div>
        <button type="button" className="pro-button is-primary" disabled={busy || scenario.trim().length < 40} onClick={() => void generate()}>
          {busy ? <Loader2 size={15} className="animate-spin" aria-hidden="true" /> : <Scale size={15} aria-hidden="true" />}Generate review draft
        </button>
      </div>
      <Notice text={notice.text} failed={notice.failed} />
      {draft && (
        <div className="pro-draft">
          <div className="pro-draft-head">
            <strong>Draft version {draft.version}, {draft.status}</strong>
            <span>{draft.missing_fields.length ? `Missing: ${draft.missing_fields.join(", ")}` : "Required facts captured"}</span>
            <div className="pro-draft-actions">
              <button type="button" className="pro-button" onClick={() => void copy(draft)}>{copied ? <Check size={13} aria-hidden="true" /> : <ClipboardCopy size={13} aria-hidden="true" />}{copied ? "Copied" : "Copy"}</button>
              <button type="button" className="pro-button" onClick={() => save(draft)}><Download size={13} aria-hidden="true" />Save</button>
            </div>
          </div>
          <pre>{draft.rendered_text}</pre>
        </div>
      )}
      <section className="pro-subsection" aria-label="FIR drafts in this case">
        <h3>FIR drafts in this case</h3>
        {listFailed && <p className="pro-quiet">The drafting history could not be read.</p>}
        {drafts && !drafts.length && <p className="pro-quiet">Nothing has been drafted in this case yet.</p>}
        {!!drafts?.length && (
          <ul className="pro-rows">
            {drafts.map((item) => (
              <li key={item.id}>
                <button type="button" className="pro-activity" disabled={busy} onClick={() => void open(item.id)}>
                  <span className="pro-due-main"><strong>{docLabel(item.doc_type)}, version {item.version}</strong>
                    {item.missing_field_count > 0 && <span className="pro-meta"><span>{plural(item.missing_field_count, "field")} missing</span></span>}
                  </span>
                  <time>{shortDate(item.created_at)}</time>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

/** Advocate: both sides of the case. An analysis opened from the overview arrives through `opened`. */
export function DefencePanel({ caseId, opened, onChanged }: { caseId: string; opened: DefenceAnalysisResponse | null; onChanged: () => void }) {
  const [scenario, setScenario] = useState(opened?.case_scenario ?? "");
  const [analysis, setAnalysis] = useState<DefenceAnalysisResponse | null>(opened);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState({ text: "", failed: false });
  useEffect(() => {
    if (opened) { setAnalysis(opened); setScenario(opened.case_scenario ?? ""); setNotice({ text: "", failed: false }); }
  }, [opened]);
  const run = async () => {
    setBusy(true); setNotice({ text: "", failed: false }); setAnalysis(null);
    try {
      const result = await analyseDefence(caseId, scenario.trim());
      setAnalysis(result);
      setNotice({ text: `Verified ${plural(result.points.length, "strategy point")}; rejected ${result.rejected_point_count}.`, failed: false });
      onChanged();
    } catch (error) { setNotice({ text: errorText(error), failed: true }); } finally { setBusy(false); }
  };
  return (
    <div className="pro-stack">
      <label className="pro-label">The case as you understand it
        <textarea className="field min-h-44 resize-y leading-6" value={scenario} placeholder="Allegations, evidence, disputed facts, procedural history and the client's position." onChange={(event) => setScenario(event.target.value)} />
        <small>At least 40 characters.</small>
      </label>
      <div>
        <button type="button" className="pro-button is-primary" disabled={busy || scenario.trim().length < 40} onClick={() => void run()}>
          {busy ? <Loader2 size={15} className="animate-spin" aria-hidden="true" /> : <Scale size={15} aria-hidden="true" />}Run two-sided analysis
        </button>
      </div>
      <Notice text={notice.text} failed={notice.failed} />
      {analysis && <DefenceAnalysisResult analysis={analysis} />}
    </div>
  );
}

/** Law and this case's files, or the files of every case the person owns. Never anyone else's. */
export function AuthoritySearch({ caseId }: { caseId: string }) {
  const [mode, setMode] = useState<"general" | "case_specific">("case_specific");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<RetrievalHit[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState({ text: "", failed: false });
  const run = async () => {
    setBusy(true); setNotice({ text: "", failed: false });
    try {
      const response = await scopedSearch(query.trim(), mode, caseId);
      setResults(response.results);
      setNotice({ text: `${plural(response.results.length, "result")} from sources you are allowed to read.`, failed: false });
    } catch (error) { setNotice({ text: errorText(error), failed: true }); } finally { setBusy(false); }
  };
  return (
    <div className="pro-stack">
      <div className="pro-segment" role="group" aria-label="Where to search">
        <button type="button" aria-pressed={mode === "case_specific"} onClick={() => setMode("case_specific")}>This case</button>
        <button type="button" aria-pressed={mode === "general"} onClick={() => setMode("general")}>All my cases</button>
      </div>
      <label className="pro-label">What to search for
        <textarea className="field min-h-28 resize-y leading-6" value={query} placeholder="Search legal authority and your own files." onChange={(event) => setQuery(event.target.value)} />
      </label>
      <div>
        <button type="button" className="pro-button is-primary" disabled={busy || !query.trim()} onClick={() => void run()}>
          {busy ? <Loader2 size={15} className="animate-spin" aria-hidden="true" /> : <FileSearch size={15} aria-hidden="true" />}Search sources
        </button>
      </div>
      <Notice text={notice.text} failed={notice.failed} />
      {results === null && <p className="pro-quiet">Searching this case also reads the files in it. Searching all your cases reads the law and the files in every case you own, and nobody else&apos;s.</p>}
      {!!results?.length && (
        <ul className="pro-results">
          {results.map((hit) => (
            <li key={`${hit.payload.collection_name}-${hit.point_id}`}>
              <div><strong>{String(hit.payload.title ?? "Private case file")}</strong><span>{Math.round(hit.reranker_score * 100)}% match</span></div>
              <p>{String(hit.payload.text ?? "")}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const CLASSES = {
  police: [["witness_statement", "Witness statement"], ["fir", "FIR or complaint"], ["forensic_report", "Forensic report"], ["seizure_record", "Seizure or chain-of-custody record"], ["order", "Court order"]],
  advocate: [["client_statement", "Client statement"], ["pleading", "Pleading or petition"], ["opponent_filing", "Opposing filing"], ["evidence_exhibit", "Evidence exhibit"], ["order", "Order or judgment"]],
} as const;

function SingleUpload({ caseId, isPolice, onUploaded }: { caseId: string; isPolice: boolean; onUploaded: () => void }) {
  const options = isPolice ? CLASSES.police : CLASSES.advocate;
  const [docType, setDocType] = useState<string>(options[0][0]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState({ text: "", failed: false });
  const upload = async (file?: File) => {
    if (!file) return;
    setBusy(true); setNotice({ text: "", failed: false });
    try {
      const stored = await uploadCaseEvidence(caseId, file);
      const indexed = await indexCaseEvidence(caseId, stored.id, docType);
      setNotice({ text: `Added ${file.name}: ${plural(indexed.pages, "page")}, ${plural(indexed.chunks, "searchable passage")}.`, failed: false });
      onUploaded();
    } catch (error) { setNotice({ text: errorText(error), failed: true }); } finally { setBusy(false); }
  };
  return (
    <div className="pro-stack">
      <label className="pro-label">What kind of file is it?
        <select className="field" value={docType} onChange={(event) => setDocType(event.target.value)}>
          {options.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          <option value="other">Other</option>
        </select>
      </label>
      <label className="pro-drop">
        {busy ? <Loader2 size={20} className="animate-spin" aria-hidden="true" /> : <UploadCloud size={20} aria-hidden="true" />}
        <strong>Choose a file to add</strong>
        <span>PDF or text. Scanned pages are read by OCR. It stays inside this case.</span>
        <input type="file" accept="application/pdf,text/plain" className="sr-only" disabled={busy} onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ""; void upload(file); }} />
      </label>
      <Notice text={notice.text} failed={notice.failed} />
    </div>
  );
}

/** The files in this case, and the way to add one. */
export function CaseFilesPanel({ caseId, isPolice, refresh, onChanged, onReview }: { caseId: string; isPolice: boolean; refresh: number; onChanged: () => void; onReview: () => void }) {
  const [files, setFiles] = useState<CaseDocumentSummary[] | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let cancelled = false;
    setFailed(false);
    listIndexedCaseDocuments(caseId)
      .then((response) => { if (!cancelled) setFiles(response.documents); })
      .catch(() => { if (!cancelled) { setFiles(null); setFailed(true); } });
    return () => { cancelled = true; };
  }, [caseId, refresh]);
  return (
    <div className="pro-stack">
      {/* FILES SLOT: see ./slots.tsx. The bulk uploader takes this place once it is plugged in. */}
      {CaseBulkUpload ? <CaseBulkUpload key={caseId} caseId={caseId} onUploaded={onChanged} /> : <SingleUpload caseId={caseId} isPolice={isPolice} onUploaded={onChanged} />}
      <section className="pro-subsection" aria-label="Files in this case">
        <h3>Files in this case</h3>
        {failed && <p className="pro-quiet">The file list could not be read.</p>}
        {files && !files.length && <p className="pro-quiet">No file has been added to this case yet.</p>}
        {!!files?.length && (
          <ul className="pro-rows">
            {files.map((item) => (
              <li key={item.document_id}>
                <button type="button" className="pro-activity" onClick={onReview}>
                  <FileText size={15} aria-hidden="true" className="flex-none" />
                  <span className="pro-due-main"><strong>{item.filename}</strong></span>
                  <time>{plural(item.page_count, "page")}, {plural(item.chunk_count, "passage")}</time>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
