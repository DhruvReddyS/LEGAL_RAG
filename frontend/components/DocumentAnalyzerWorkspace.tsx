"use client";

import { AlertTriangle, CheckCircle2, FileSearch2, Fingerprint, Loader2, ScanSearch, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { analyzeCaseDocument, ApiError, getLatestDocumentAnalysis, listIndexedCaseDocuments } from "@/lib/api";
import type { CaseDocumentSummary, DocumentAnalysisResponse, DocumentFinding, SourceEvidence } from "@/lib/types";
import SourceInspector from "@/components/SourceInspector";

function errorText(error: unknown): string {
  return error instanceof ApiError ? error.message : "Document analysis failed. Check Ollama and try again.";
}

function FindingList({ title, items, onInspect }: { title: string; items: DocumentFinding[]; onInspect: (source: SourceEvidence) => void }) {
  return <section><div className="mb-2 flex items-center justify-between"><h4 className="text-xs font-semibold text-[var(--ink-soft)]">{title}</h4><span className="text-[10px] text-[var(--ink-soft)]">{items.length} grounded</span></div><div className="space-y-2">{items.map((item, index) => <article key={`${title}-${index}`} className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-4"><div className="flex items-start gap-3"><span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${item.severity === "high" ? "bg-[var(--state-bad-text)]" : item.severity === "review" ? "bg-[var(--state-warn-text)]" : "bg-[var(--accent)]"}`} /><div className="min-w-0 flex-1"><p className="text-sm leading-6 text-[var(--ink)]">{item.text}</p><div className="mt-3 flex flex-wrap gap-2">{item.evidence.map((source) => <button key={source.point_id} onClick={() => onInspect(source)} className="rounded-lg border border-[var(--border)] bg-[var(--hover)] px-2.5 py-1.5 text-[10px] font-semibold text-[var(--accent)] hover:bg-[var(--hover)]">p. {source.page_start} / inspect evidence</button>)}</div></div></div></article>)}</div></section>;
}

export default function DocumentAnalyzerWorkspace({ caseId, role, refreshToken }: { caseId: string; role: string; refreshToken: number }) {
  const [documents, setDocuments] = useState<CaseDocumentSummary[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [focus, setFocus] = useState("");
  const [analysis, setAnalysis] = useState<DocumentAnalysisResponse | null>(null);
  const [inspector, setInspector] = useState<SourceEvidence | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const selected = useMemo(() => documents.find((item) => item.document_id === selectedId), [documents, selectedId]);

  useEffect(() => {
    if (!caseId) { setDocuments([]); setSelectedId(""); return; }
    let active = true;
    listIndexedCaseDocuments(caseId).then((response) => { if (!active) return; setDocuments(response.documents); setSelectedId((current) => response.documents.some((item) => item.document_id === current) ? current : response.documents[0]?.document_id ?? ""); }).catch((reason) => active && setError(errorText(reason)));
    return () => { active = false; };
  }, [caseId, refreshToken]);

  useEffect(() => {
    if (!caseId || !selectedId) { setAnalysis(null); return; }
    let active = true;
    getLatestDocumentAnalysis(caseId, selectedId)
      .then((result) => { if (active) setAnalysis(result); })
      .catch((reason) => { if (active && (!(reason instanceof ApiError) || reason.status !== 404)) setError(errorText(reason)); });
    return () => { active = false; };
  }, [caseId, selectedId]);

  const run = async () => {
    if (!caseId || !selectedId || busy) return;
    setBusy(true); setError(""); setAnalysis(null);
    try { setAnalysis(await analyzeCaseDocument(caseId, selectedId, focus)); }
    catch (reason) { setError(errorText(reason)); }
    finally { setBusy(false); }
  };

  return <>
    <section id="document-analyzer" className="panel scroll-mt-24 overflow-hidden 2xl:col-span-2">
      <header className="flex flex-col justify-between gap-3 border-b border-[var(--border)] px-5 py-4 sm:flex-row sm:items-center"><div><h3 className="flex items-center gap-2 text-sm font-semibold"><ScanSearch size={17} className="text-[var(--accent)]" />Document Analyzer</h3><p className="mt-1 text-xs text-[var(--ink-soft)]">Structured evidence review with corpus-cross-checked legal sections</p></div><span className="flex items-center gap-1.5 rounded-full bg-[var(--state-ok-bg)] px-2.5 py-1.5 text-[10px] font-semibold text-[var(--state-ok-text)]"><ShieldCheck size={13} />{role === "police" ? "POLICE EVIDENCE PROFILE" : "ADVOCATE REVIEW PROFILE"}</span></header>
      <div className="grid lg:grid-cols-[300px_minmax(0,1fr)]">
        <aside className="border-b border-[var(--border)] bg-[var(--card)] p-4 lg:border-b-0 lg:border-r"><p className="text-[10px] font-semibold text-[var(--ink-soft)]">Indexed evidence library</p><div className="mt-3 space-y-2">{documents.map((document) => <button key={document.document_id} onClick={() => { setSelectedId(document.document_id); setAnalysis(null); }} className={`w-full rounded-xl border p-3 text-left transition ${selectedId === document.document_id ? "border-[var(--state-warn-line)] bg-[var(--card)] shadow-sm" : "border-transparent hover:bg-[var(--card)]"}`}><div className="flex items-start gap-2"><Fingerprint size={15} className="mt-0.5 shrink-0 text-[var(--accent)]" /><div className="min-w-0"><p className="truncate text-xs font-semibold text-[var(--ink)]">{document.filename}</p><p className="mt-1 text-[10px] capitalize text-[var(--ink-soft)]">{document.doc_type.replaceAll("_", " ")} / {document.page_count} pages / {document.chunk_count} passages</p></div></div></button>)}{!documents.length && <div className="rounded-xl border border-dashed border-[var(--border)] bg-[var(--card)] px-4 py-8 text-center"><FileSearch2 size={22} className="mx-auto text-[var(--ink-soft)]" /><p className="mt-2 text-xs text-[var(--ink-soft)]">Upload and index evidence above to begin analysis.</p></div>}</div></aside>
        <div className="min-w-0 p-5">
          {selected ? <><div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start"><div><p className="text-[10px] font-semibold text-[var(--accent)]">Selected document</p><h4 className="mt-1 text-base font-semibold text-[var(--ink)]">{selected.filename}</h4><p className="mt-1 text-xs text-[var(--ink-soft)]">SHA-256 {selected.sha256?.slice(0, 16) ?? "unavailable"}… / private matter index</p></div><span className="rounded-full border border-[var(--state-ok-line)] bg-[var(--state-ok-bg)] px-2.5 py-1 text-[10px] font-semibold text-[var(--state-ok-text)]">Index verified</span></div><textarea value={focus} onChange={(event) => setFocus(event.target.value)} placeholder={role === "police" ? "Optional focus: event chronology, witness gaps, identifiers, chain of custody…" : "Optional focus: obligations, admissions, contradictions, adverse clauses, missing proof…"} className="mt-4 min-h-24 w-full rounded-xl border border-[var(--border)] p-3.5 text-sm outline-none focus:border-[var(--accent)] focus:ring-4 focus:ring-[var(--accent)]/10" /><button onClick={run} disabled={busy} className="button-primary mt-3">{busy ? <Loader2 size={15} className="animate-spin" /> : <ScanSearch size={15} />}Analyse document</button></> : <p className="py-16 text-center text-sm text-[var(--ink-soft)]">Select indexed evidence to analyse.</p>}
          {error && <div role="alert" className="mt-4 flex items-start gap-2 rounded-xl border border-[var(--state-bad-line)] bg-[var(--state-bad-bg)] p-3 text-xs text-[var(--state-bad-text)]"><AlertTriangle size={15} className="mt-0.5 shrink-0" />{error}</div>}
          {analysis && <div className="mt-6 border-t border-[var(--border)] pt-6"><div className="rounded-2xl bg-[var(--ink)] p-5 text-[var(--paper)]"><div className="flex flex-wrap items-center justify-between gap-2"><p className="text-[10px] font-semibold text-[var(--ink-soft)]">Analysis version {analysis.version}</p><span className="text-[10px] text-slate-400">{analysis.analyzed_chunk_count}/{analysis.total_chunk_count} passages reviewed</span></div><p className="mt-3 text-sm leading-6 text-slate-200">{analysis.summary}</p>{analysis.partial_review && <p className="mt-3 text-xs text-[var(--state-warn-line)]">Partial representative review—inspect the original before relying on omitted passages.</p>}</div><div className="mt-5 grid gap-5 xl:grid-cols-2"><FindingList title="Key clauses & facts" items={analysis.key_clauses} onInspect={setInspector} /><FindingList title="Risks & review points" items={analysis.risks} onInspect={setInspector} /></div><section className="mt-5"><div className="mb-2 flex items-center justify-between"><h4 className="text-xs font-semibold text-[var(--ink-soft)]">Corpus-verified applicable sections</h4><span className="text-[10px] text-[var(--ink-soft)]">{analysis.rejected_section_count} unsupported rejected</span></div><div className="grid gap-2 lg:grid-cols-2">{analysis.applicable_sections.map((item) => <button key={`${item.label}-${item.evidence.point_id}`} onClick={() => setInspector(item.evidence)} className="rounded-xl border border-[var(--state-ok-line)] bg-[var(--state-ok-bg)] p-4 text-left"><div className="flex items-center gap-2 text-xs font-semibold text-[var(--state-ok-text)]"><CheckCircle2 size={14} />{item.label}</div><p className="mt-2 text-xs leading-5 text-[var(--ink-soft)]">{item.rationale}</p><p className="mt-3 text-[10px] font-semibold text-[var(--accent)]">Inspect authority / p. {item.evidence.page_start}</p></button>)}{!analysis.applicable_sections.length && <div className="rounded-xl border border-[var(--state-warn-line)] bg-[var(--state-warn-bg)] p-4 text-xs text-[var(--state-warn-text)]">No proposed section passed corpus cross-verification. Treat the document as evidence only.</div>}</div></section><p className="mt-5 text-xs leading-5 text-[var(--ink-soft)]">{analysis.disclaimer}</p></div>}
        </div>
      </div>
    </section>
    {inspector && <SourceInspector source={inspector} onClose={() => setInspector(null)} />}
  </>;
}
