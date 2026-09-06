"use client";

import { BriefcaseBusiness, CalendarClock, ClipboardCheck, ScanText, CheckCircle2, ChevronRight, FileCheck2, FileSearch, Fingerprint, FolderPlus, Loader2, Plus, Scale, ScanSearch, ShieldCheck, UploadCloud } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { AuthorityCheck } from "@/components/AuthorityCheck";
import { ComplianceChecklist } from "@/components/ComplianceChecklist";
import { InvestigationTimeline } from "@/components/InvestigationTimeline";
import { ApiError, analyseDefence, createCase, draftFir, indexCaseEvidence, listCases, scopedSearch, uploadCaseEvidence } from "@/lib/api";
import type { DefenceAnalysisResponse, FIRDraftResponse, LegalCase, RetrievalHit, User } from "@/lib/types";
import DocumentAnalyzerWorkspace from "@/components/DocumentAnalyzerWorkspace";

function errorText(error: unknown): string { return error instanceof ApiError ? error.message : "The operation failed. Check the backend and try again."; }

export default function ProfessionalWorkspace({ user }: { user: User }) {
  const isPolice = user.role === "police";
  const roleCopy = isPolice ? {
    eyebrow: "Police investigation operations",
    matters: "Investigation matters",
    description: "Lawful procedure, investigation records and ownership-isolated police evidence.",
    intake: "Investigation evidence intake",
    search: "Procedure & evidence search",
  } : {
    eyebrow: "Advocate matter operations",
    matters: "Client matters",
    description: "Two-sided authority research and ownership-isolated client evidence.",
    intake: "Client evidence intake",
    search: "Authority & matter search",
  };
  const [cases, setCases] = useState<LegalCase[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [newTitle, setNewTitle] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [searchMode, setSearchMode] = useState<"general" | "case_specific">("case_specific");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<RetrievalHit[]>([]);
  const [docType, setDocType] = useState(isPolice ? "witness_statement" : "client_statement");
  const [scenario, setScenario] = useState("");
  const [draft, setDraft] = useState<FIRDraftResponse | null>(null);
  const [analysis, setAnalysis] = useState<DefenceAnalysisResponse | null>(null);
  const [documentRefresh, setDocumentRefresh] = useState(0);
  const selected = useMemo(() => cases.find((item) => item.id === selectedId), [cases, selectedId]);
  const jumpTo = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });

  useEffect(() => { listCases().then((response) => { setCases(response.cases); setSelectedId(response.cases[0]?.id ?? ""); }).catch((error) => setNotice(errorText(error))); }, []);

  const makeCase = async () => {
    if (newTitle.trim().length < 3) return; setBusy("case"); setNotice("");
    try { const created = await createCase(newTitle.trim()); setCases((current) => [created, ...current]); setSelectedId(created.id); setNewTitle(""); setNotice("Case workspace created with private role-scoped storage."); }
    catch (error) { setNotice(errorText(error)); } finally { setBusy(null); }
  };
  const search = async () => {
    if (!searchQuery.trim() || (searchMode === "case_specific" && !selectedId)) return; setBusy("search"); setNotice("");
    try { const response = await scopedSearch(searchQuery.trim(), searchMode, selectedId); setSearchResults(response.results); setNotice(`Retrieved ${response.results.length} authorised public and private results.`); }
    catch (error) { setNotice(errorText(error)); } finally { setBusy(null); }
  };
  const upload = async (file?: File) => {
    if (!file || !selectedId) return; setBusy("upload"); setNotice("");
    try { const stored = await uploadCaseEvidence(selectedId, file); const indexed = await indexCaseEvidence(selectedId, stored.id, docType); setDocumentRefresh((value) => value + 1); setNotice(`Indexed ${file.name}: ${indexed.pages} page(s), ${indexed.chunks} private passage(s). It is ready in Document Analyzer.`); }
    catch (error) { setNotice(errorText(error)); } finally { setBusy(null); }
  };
  const runProfessionalTool = async () => {
    if (!selectedId || scenario.trim().length < 40) return; setBusy("tool"); setNotice(""); setDraft(null); setAnalysis(null);
    try {
      if (user.role === "police") { const result = await draftFir(selectedId, scenario.trim()); setDraft(result); setNotice(`Created immutable FIR draft version ${result.version}.`); }
      else { const result = await analyseDefence(selectedId, scenario.trim()); setAnalysis(result); setNotice(`Verified ${result.points.length} strategy point(s); rejected ${result.rejected_point_count}.`); }
    } catch (error) { setNotice(errorText(error)); } finally { setBusy(null); }
  };

  return (
    <section className="mx-auto max-w-[1440px] px-5 py-7 md:px-8 md:py-9">
      <div className="mb-7 flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div><p className="eyebrow">{roleCopy.eyebrow}</p><h2 className="mt-2 text-3xl font-semibold tracking-[-0.035em]">{selected?.title ?? "Case workspace"}</h2><p className="mt-2 text-sm text-[var(--ink-soft)]">{roleCopy.description}</p></div>
        <div className="flex items-center gap-2 rounded-full border border-[var(--state-ok-line)] bg-[var(--state-ok-bg)] px-3 py-1.5 text-xs font-medium text-[var(--state-ok-text)]"><ShieldCheck size={14} /> Role isolation active</div>
      </div>
      <nav aria-label="Matter tools" className="workspace-tools">
        <button onClick={()=>jumpTo("role-agent-tool")}><Scale size={17}/>{isPolice ? "FIR draft" : "Strategy"}</button>
        {isPolice && <button onClick={()=>jumpTo("investigation-timeline")}><CalendarClock size={17}/>Deadlines</button>}
        {isPolice && <button onClick={()=>jumpTo("investigation-compliance")}><ClipboardCheck size={17}/>Compliance</button>}
        <button onClick={()=>jumpTo("authority-check")}><ScanText size={17}/>Check citations</button>
        <button onClick={()=>jumpTo("role-scoped-search")}><FileSearch size={17}/>Find authority</button>
        <button onClick={()=>jumpTo("role-evidence-intake")}><UploadCloud size={17}/>Add evidence</button>
        <button onClick={()=>jumpTo("document-analyzer")}><ScanSearch size={17}/>Review documents</button>
      </nav>
      {notice && <div role="status" className="mb-5 flex items-center gap-2 rounded-xl border border-[var(--state-ok-line)] bg-[var(--state-ok-bg)] px-4 py-3 text-sm text-[var(--state-ok-text)]"><CheckCircle2 size={16} />{notice}</div>}

      <div className="grid gap-5 xl:grid-cols-[270px_minmax(0,1fr)]">
        <aside className="panel h-fit overflow-hidden">
          <div className="border-b border-[var(--border)] px-4 py-4"><div className="flex items-center gap-2 text-sm font-semibold"><BriefcaseBusiness size={17} className="text-[var(--accent)]" />{roleCopy.matters}</div></div>
          <div className="p-3"><div className="flex gap-2"><input value={newTitle} onChange={(event) => setNewTitle(event.target.value)} placeholder="New matter title" className="field h-10 min-w-0 flex-1" /><button onClick={makeCase} aria-label="Create case" disabled={busy === "case" || newTitle.trim().length < 3} className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--ink)] text-[var(--paper)] disabled:opacity-40">{busy === "case" ? <Loader2 size={15} className="animate-spin" /> : <Plus size={17} />}</button></div>
            <div className="mt-3 space-y-1.5">{cases.map((item) => <button key={item.id} onClick={() => setSelectedId(item.id)} className={`group w-full rounded-xl p-3 text-left transition ${selectedId === item.id ? "bg-[var(--hover)]" : "hover:bg-[var(--hover)]"}`}><div className="flex items-start gap-2"><div className={`mt-1.5 h-2 w-2 rounded-full ${item.status === "open" ? "bg-[var(--state-ok-text)]" : "bg-[var(--ink-soft)]"}`} /><div className="min-w-0 flex-1"><span className="block truncate text-sm font-medium text-[var(--ink)]">{item.title}</span><span className="mt-1 block text-[10px] text-[var(--ink-soft)]">{item.status} / {item.role_type}</span></div><ChevronRight size={14} className="mt-1 text-[var(--ink-soft)]" /></div></button>)}{!cases.length && <div className="py-10 text-center"><FolderPlus size={25} className="mx-auto text-[var(--ink-soft)]" /><p className="mt-2 text-xs text-[var(--ink-soft)]">Create a matter to begin</p></div>}</div>
          </div>
        </aside>

        <div className="grid min-w-0 gap-5 2xl:grid-cols-2">
          <div id="role-scoped-search" className="panel scroll-mt-24 overflow-hidden">
            <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-4"><h3 className="flex items-center gap-2 text-sm font-semibold"><FileSearch size={17} className="text-[var(--accent)]" />{roleCopy.search}</h3><span className="text-[10px] text-[var(--ink-soft)]">Public + authorised private</span></div>
            <div className="p-5">
              <div className="inline-flex rounded-lg bg-[var(--hover)] p-1"><button onClick={() => setSearchMode("case_specific")} className={`rounded-md px-3 py-1.5 text-xs font-medium ${searchMode === "case_specific" ? "bg-[var(--card)] text-[var(--ink)] shadow-sm" : "text-[var(--ink-soft)]"}`}>Selected matter</button><button onClick={() => setSearchMode("general")} className={`rounded-md px-3 py-1.5 text-xs font-medium ${searchMode === "general" ? "bg-[var(--card)] text-[var(--ink)] shadow-sm" : "text-[var(--ink-soft)]"}`}>All my matters</button></div>
              <textarea value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} placeholder="Search legal authority and authorised evidence…" className="mt-4 min-h-28 w-full resize-y rounded-xl border border-[var(--border)] p-3.5 text-sm outline-none focus:border-[var(--accent)] focus:ring-4 focus:ring-[var(--accent)]/10" />
              <button onClick={search} disabled={busy === "search" || !selectedId} className="button-primary mt-3">{busy === "search" ? <Loader2 size={15} className="animate-spin" /> : <FileSearch size={15} />}Search sources</button>
              <div className="mt-5 max-h-80 space-y-2 overflow-auto">{searchResults.map((hit) => <article key={`${hit.payload.collection_name}-${hit.point_id}`} className="rounded-xl border border-[var(--border)] p-3.5"><div className="flex items-center justify-between gap-3"><p className="truncate text-xs font-semibold text-[var(--accent)]">{String(hit.payload.title ?? "Private case evidence")}</p><span className="text-[10px] text-[var(--ink-soft)]">{Math.round(hit.reranker_score * 100)}% match</span></div><p className="mt-2 line-clamp-4 text-xs leading-5 text-[var(--ink-soft)]">{String(hit.payload.text ?? "")}</p></article>)}</div>
            </div>
          </div>

          <div id="role-evidence-intake" className="panel scroll-mt-24 overflow-hidden">
            <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-4"><h3 className="flex items-center gap-2 text-sm font-semibold"><UploadCloud size={17} className="text-[var(--accent)]" />{roleCopy.intake}</h3><span className="rounded-full bg-[var(--hover)] px-2 py-1 text-[10px] font-medium text-[var(--ink-soft)]">Private index</span></div>
            <div className="p-5"><p className="text-xs leading-5 text-[var(--ink-soft)]">Add a PDF or UTF-8 statement. Scanned pages are OCR processed and indexed only for this role and matter.</p>
              <label className="mt-4 block text-xs font-medium text-[var(--ink)]">Evidence classification<select value={docType} onChange={(event) => setDocType(event.target.value)} className="field mt-2">{isPolice ? <><option value="witness_statement">Witness statement</option><option value="fir">FIR / complaint</option><option value="forensic_report">Forensic report</option><option value="seizure_record">Seizure / chain-of-custody record</option><option value="order">Court order</option></> : <><option value="client_statement">Client statement</option><option value="pleading">Pleading / petition</option><option value="opponent_filing">Opposing filing</option><option value="evidence_exhibit">Evidence exhibit</option><option value="order">Order / judgment</option></>}<option value="other">Other evidence</option></select></label>
              <label className="mt-4 flex min-h-36 cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-[var(--border)] bg-[var(--hover)] px-4 text-center transition hover:bg-[var(--hover)]"><div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--card)] text-[var(--accent)] shadow-sm">{busy === "upload" ? <Loader2 size={19} className="animate-spin" /> : <UploadCloud size={19} />}</div><p className="mt-3 text-sm font-medium text-[var(--ink)]">Choose evidence to upload</p><p className="mt-1 text-xs text-[var(--ink-soft)]">PDF or TXT / private to this matter</p><input type="file" accept="application/pdf,text/plain" className="hidden" disabled={!selectedId || busy === "upload"} onChange={(event) => upload(event.target.files?.[0])} /></label>
            </div>
          </div>

          {isPolice && (
            <div id="investigation-timeline" className="panel scroll-mt-24 overflow-hidden 2xl:col-span-2">
              <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-4">
                <h3 className="flex items-center gap-2 text-sm font-semibold"><CalendarClock size={17} className="text-[var(--accent)]" />Investigation deadlines</h3>
                <span className="flex items-center gap-1.5 text-[10px] font-medium text-[var(--state-ok-text)]"><ShieldCheck size={13} />Computed, not generated</span>
              </div>
              <div className="p-5"><InvestigationTimeline caseId={selectedId} /></div>
            </div>
          )}

          {isPolice && (
            <div id="investigation-compliance" className="panel scroll-mt-24 overflow-hidden 2xl:col-span-2">
              <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-4">
                <h3 className="flex items-center gap-2 text-sm font-semibold"><ClipboardCheck size={17} className="text-[var(--accent)]" />BNSS compliance record</h3>
                <span className="flex items-center gap-1.5 text-[10px] font-medium text-[var(--state-ok-text)]"><ShieldCheck size={13} />Read from the Sanhita</span>
              </div>
              <div className="p-5"><ComplianceChecklist caseId={selectedId} /></div>
            </div>
          )}

          <div id="authority-check" className="panel scroll-mt-24 overflow-hidden 2xl:col-span-2">
            <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-4">
              <h3 className="flex items-center gap-2 text-sm font-semibold"><ScanText size={17} className="text-[var(--accent)]" />Citation currency check</h3>
              <span className="flex items-center gap-1.5 text-[10px] font-medium text-[var(--state-ok-text)]"><ShieldCheck size={13} />Official concordance</span>
            </div>
            <div className="p-5"><AuthorityCheck caseId={selectedId} /></div>
          </div>

          <DocumentAnalyzerWorkspace caseId={selectedId} role={user.role} refreshToken={documentRefresh} />

          <div id="role-agent-tool" className="panel scroll-mt-24 overflow-hidden 2xl:col-span-2">
            <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-4"><h3 className="flex items-center gap-2 text-sm font-semibold"><Scale size={17} className="text-[var(--accent)]" />{user.role === "police" ? "FIR drafting assistant" : "Defence analysis workspace"}</h3><span className="flex items-center gap-1.5 text-[10px] font-medium text-[var(--state-ok-text)]"><ShieldCheck size={13} />Grounded review</span></div>
            <div className="p-5"><p className="max-w-3xl text-xs leading-5 text-[var(--ink-soft)]">{user.role === "police" ? "Record known facts only. Unknown fields remain visibly incomplete and every suggested provision is retrieved for professional review." : "Analyse allegations, evidence and procedure from both sides. Unsupported or unsafe tactics are rejected before results are returned."}</p>
              <textarea value={scenario} onChange={(event) => setScenario(event.target.value)} placeholder={user.role === "police" ? "Enter the complainant account, dates, location, property or person description, witnesses and known circumstances…" : "Describe allegations, evidence, disputed facts, procedural history and the client position…"} className="mt-4 min-h-40 w-full resize-y rounded-xl border border-[var(--border)] p-4 text-sm leading-6 outline-none focus:border-[var(--accent)] focus:ring-4 focus:ring-[var(--accent)]/10" />
              <button onClick={runProfessionalTool} disabled={!selectedId || busy === "tool" || scenario.trim().length < 40} className="button-primary mt-3">{busy === "tool" ? <Loader2 size={15} className="animate-spin" /> : <Scale size={15} />}{user.role === "police" ? "Generate review draft" : "Run two-sided analysis"}</button>
              {draft && <div className="mt-6 rounded-xl border border-[var(--border)]"><div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border)] bg-[var(--card)] px-4 py-3"><p className="text-xs font-semibold">Draft version {draft.version} / {draft.status}</p><p className="text-[11px] text-[var(--state-warn-text)]">{draft.missing_fields.length ? `Missing: ${draft.missing_fields.join(", ")}` : "Required facts captured"}</p></div><pre className="max-h-[520px] overflow-auto whitespace-pre-wrap p-5 text-xs leading-6 text-[var(--ink)]">{draft.rendered_text}</pre></div>}
              {analysis && <div className="mt-6"><div className="rounded-xl bg-[var(--hover)] p-4 text-sm leading-6 text-[var(--ink)]">{analysis.summary}</div><div className="mt-3 grid gap-3 lg:grid-cols-2">{analysis.points.map((point, index) => <article key={`${point.category}-${index}`} className="rounded-xl border border-[var(--border)] p-4"><p className="text-[10px] font-semibold text-[var(--accent)]">{point.category.replaceAll("_", " ")} / {point.verification}</p><p className="mt-2 text-sm leading-6 text-[var(--ink)]">{point.point}</p></article>)}</div><p className="mt-4 text-xs text-[var(--ink-soft)]">{analysis.disclaimer}</p></div>}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
