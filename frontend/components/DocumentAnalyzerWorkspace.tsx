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
  return <section><div className="mb-2 flex items-center justify-between"><h4 className="text-xs font-semibold uppercase tracking-[.13em] text-[#667085]">{title}</h4><span className="text-[10px] text-[#98a2b3]">{items.length} grounded</span></div><div className="space-y-2">{items.map((item, index) => <article key={`${title}-${index}`} className="rounded-xl border border-[#e4e7ec] bg-white p-4"><div className="flex items-start gap-3"><span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${item.severity === "high" ? "bg-[#d92d20]" : item.severity === "review" ? "bg-[#f79009]" : "bg-[#167184]"}`} /><div className="min-w-0 flex-1"><p className="text-sm leading-6 text-[#344054]">{item.text}</p><div className="mt-3 flex flex-wrap gap-2">{item.evidence.map((source) => <button key={source.point_id} onClick={() => onInspect(source)} className="rounded-lg border border-[#c9dfe2] bg-[#f2f9f9] px-2.5 py-1.5 text-[10px] font-semibold text-[#167184] hover:bg-[#e8f4f5]">p. {source.page_start} · inspect evidence</button>)}</div></div></div></article>)}</div></section>;
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
      <header className="flex flex-col justify-between gap-3 border-b border-[#e4e7ec] px-5 py-4 sm:flex-row sm:items-center"><div><h3 className="flex items-center gap-2 text-sm font-semibold"><ScanSearch size={17} className="text-[#167184]" />Document Analyzer</h3><p className="mt-1 text-xs text-[#667085]">Structured evidence review with corpus-cross-checked legal sections</p></div><span className="flex items-center gap-1.5 rounded-full bg-[#eef8f2] px-2.5 py-1.5 text-[10px] font-semibold text-[#16734a]"><ShieldCheck size={13} />{role === "police" ? "POLICE EVIDENCE PROFILE" : "ADVOCATE REVIEW PROFILE"}</span></header>
      <div className="grid lg:grid-cols-[300px_minmax(0,1fr)]">
        <aside className="border-b border-[#e4e7ec] bg-[#fafbfc] p-4 lg:border-b-0 lg:border-r"><p className="text-[10px] font-semibold uppercase tracking-[.15em] text-[#98a2b3]">Indexed evidence library</p><div className="mt-3 space-y-2">{documents.map((document) => <button key={document.document_id} onClick={() => { setSelectedId(document.document_id); setAnalysis(null); }} className={`w-full rounded-xl border p-3 text-left transition ${selectedId === document.document_id ? "border-[#94c2c8] bg-white shadow-sm" : "border-transparent hover:bg-white"}`}><div className="flex items-start gap-2"><Fingerprint size={15} className="mt-0.5 shrink-0 text-[#167184]" /><div className="min-w-0"><p className="truncate text-xs font-semibold text-[#344054]">{document.filename}</p><p className="mt-1 text-[10px] capitalize text-[#98a2b3]">{document.doc_type.replaceAll("_", " ")} · {document.page_count} pages · {document.chunk_count} passages</p></div></div></button>)}{!documents.length && <div className="rounded-xl border border-dashed border-[#d0d5dd] bg-white px-4 py-8 text-center"><FileSearch2 size={22} className="mx-auto text-[#aeb6c2]" /><p className="mt-2 text-xs text-[#667085]">Upload and index evidence above to begin analysis.</p></div>}</div></aside>
        <div className="min-w-0 p-5">
          {selected ? <><div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start"><div><p className="text-[10px] font-semibold uppercase tracking-[.14em] text-[#167184]">Selected document</p><h4 className="mt-1 text-base font-semibold text-[#344054]">{selected.filename}</h4><p className="mt-1 text-xs text-[#98a2b3]">SHA-256 {selected.sha256?.slice(0, 16) ?? "unavailable"}… · private matter index</p></div><span className="rounded-full border border-[#d7eadf] bg-[#f1faf5] px-2.5 py-1 text-[10px] font-semibold text-[#16734a]">INDEX VERIFIED</span></div><textarea value={focus} onChange={(event) => setFocus(event.target.value)} placeholder={role === "police" ? "Optional focus: event chronology, witness gaps, identifiers, chain of custody…" : "Optional focus: obligations, admissions, contradictions, adverse clauses, missing proof…"} className="mt-4 min-h-24 w-full rounded-xl border border-[#d0d5dd] p-3.5 text-sm outline-none focus:border-[#167184] focus:ring-4 focus:ring-[#167184]/10" /><button onClick={run} disabled={busy} className="button-primary mt-3">{busy ? <Loader2 size={15} className="animate-spin" /> : <ScanSearch size={15} />}Analyse document</button></> : <p className="py-16 text-center text-sm text-[#98a2b3]">Select indexed evidence to analyse.</p>}
          {error && <div role="alert" className="mt-4 flex items-start gap-2 rounded-xl border border-[#f3c7c3] bg-[#fff5f4] p-3 text-xs text-[#b42318]"><AlertTriangle size={15} className="mt-0.5 shrink-0" />{error}</div>}
          {analysis && <div className="mt-6 border-t border-[#e4e7ec] pt-6"><div className="rounded-2xl bg-[#0b1729] p-5 text-white"><div className="flex flex-wrap items-center justify-between gap-2"><p className="text-[10px] font-semibold uppercase tracking-[.14em] text-[#8ecbd0]">Analysis version {analysis.version}</p><span className="text-[10px] text-slate-400">{analysis.analyzed_chunk_count}/{analysis.total_chunk_count} passages reviewed</span></div><p className="mt-3 text-sm leading-6 text-slate-200">{analysis.summary}</p>{analysis.partial_review && <p className="mt-3 text-xs text-[#f5d8a6]">Partial representative review—inspect the original before relying on omitted passages.</p>}</div><div className="mt-5 grid gap-5 xl:grid-cols-2"><FindingList title="Key clauses & facts" items={analysis.key_clauses} onInspect={setInspector} /><FindingList title="Risks & review points" items={analysis.risks} onInspect={setInspector} /></div><section className="mt-5"><div className="mb-2 flex items-center justify-between"><h4 className="text-xs font-semibold uppercase tracking-[.13em] text-[#667085]">Corpus-verified applicable sections</h4><span className="text-[10px] text-[#98a2b3]">{analysis.rejected_section_count} unsupported rejected</span></div><div className="grid gap-2 lg:grid-cols-2">{analysis.applicable_sections.map((item) => <button key={`${item.label}-${item.evidence.point_id}`} onClick={() => setInspector(item.evidence)} className="rounded-xl border border-[#cce6d7] bg-[#f4fbf7] p-4 text-left"><div className="flex items-center gap-2 text-xs font-semibold text-[#16734a]"><CheckCircle2 size={14} />{item.label}</div><p className="mt-2 text-xs leading-5 text-[#667085]">{item.rationale}</p><p className="mt-3 text-[10px] font-semibold text-[#167184]">Inspect authority · p. {item.evidence.page_start}</p></button>)}{!analysis.applicable_sections.length && <div className="rounded-xl border border-[#f0d8ad] bg-[#fff8eb] p-4 text-xs text-[#805b24]">No proposed section passed corpus cross-verification. Treat the document as evidence only.</div>}</div></section><p className="mt-5 text-xs leading-5 text-[#667085]">{analysis.disclaimer}</p></div>}
        </div>
      </div>
    </section>
    {inspector && <SourceInspector source={inspector} onClose={() => setInspector(null)} />}
  </>;
}
