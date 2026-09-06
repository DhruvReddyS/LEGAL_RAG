"use client";

import { BriefcaseBusiness, CalendarClock, ClipboardCheck, ScanText, CheckCircle2, FileSearch, FolderPlus, Loader2, Plus, Scale, ScanSearch, ShieldCheck, UploadCloud } from "lucide-react";
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
  const [view, setView] = useState<ViewKey>("agent");
  const selected = useMemo(() => cases.find((item) => item.id === selectedId), [cases, selectedId]);

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


type ViewKey = "agent" | "deadlines" | "compliance" | "citations" | "search" | "evidence" | "documents";

  const tools: { key: ViewKey; label: string; icon: typeof Scale; title: string; blurb: string; needsMatter: boolean }[] = [
    {
      key: "agent",
      label: isPolice ? "FIR draft" : "Defence analysis",
      icon: Scale,
      title: isPolice ? "FIR drafting assistant" : "Defence analysis",
      blurb: isPolice
        ? "Record known facts only. Unknown fields stay visibly incomplete and every suggested provision is retrieved for professional review."
        : "Analyse allegations, evidence and procedure from both sides. Unsupported or unsafe tactics are rejected before results are returned.",
      needsMatter: true,
    },
    ...(isPolice
      ? ([
          {
            key: "deadlines" as ViewKey,
            label: "Deadlines",
            icon: CalendarClock,
            title: "Investigation deadlines",
            blurb: "Nine BNSS time limits, computed by date arithmetic rather than generated. A date left blank produces a stated unknown, never a guess.",
            needsMatter: true,
          },
          {
            key: "compliance" as ViewKey,
            label: "Compliance",
            icon: ClipboardCheck,
            title: "BNSS compliance record",
            blurb: "What the Sanhita requires to be recorded for an arrest, a search, the case diary and the final report. Nothing is assumed done.",
            needsMatter: true,
          },
        ])
      : []),
    {
      key: "citations",
      label: "Check citations",
      icon: ScanText,
      title: "Citation currency check",
      blurb: "Paste a draft. Every provision it cites is checked against the codes in force using the official concordance — no model reads the text.",
      needsMatter: true,
    },
    {
      key: "search",
      label: "Find authority",
      icon: FileSearch,
      title: roleCopy.search,
      blurb: "Search the governed corpus and, when a matter is selected, its private evidence. Results never cross a matter boundary.",
      needsMatter: false,
    },
    {
      key: "evidence",
      label: "Add evidence",
      icon: UploadCloud,
      title: roleCopy.intake,
      blurb: "A PDF or UTF-8 statement. Scanned pages are OCR processed and indexed only for this role and this matter.",
      needsMatter: true,
    },
    {
      key: "documents",
      label: "Review documents",
      icon: ScanSearch,
      title: "Document analyzer",
      blurb: "Read what was indexed for this matter, with the passage, its pages and its current-law status.",
      needsMatter: true,
    },
  ];
  const current = tools.find((tool) => tool.key === view) ?? tools[0];

  return (
    <section className="mx-auto max-w-[1440px] px-5 py-7 md:px-8 md:py-9">
      <div className="mb-6 flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div>
          <p className="eyebrow">{roleCopy.eyebrow}</p>
          <h2 className="mt-2 text-3xl font-semibold tracking-[-0.035em]">{selected?.title ?? roleCopy.matters}</h2>
          <p className="mt-2 text-sm text-[var(--ink-soft)]">{roleCopy.description}</p>
        </div>
        <div className="flex flex-none items-center gap-2 rounded-full border border-[var(--state-ok-line)] bg-[var(--state-ok-bg)] px-3 py-1.5 text-xs font-medium text-[var(--state-ok-text)]">
          <ShieldCheck size={14} /> Role isolation active
        </div>
      </div>

      {notice && (
        <div role="status" className="mb-5 flex items-center gap-2 rounded-xl border border-[var(--state-ok-line)] bg-[var(--state-ok-bg)] px-4 py-3 text-sm text-[var(--state-ok-text)]">
          <CheckCircle2 size={16} />{notice}
        </div>
      )}

      <div className="matter-shell">
        <aside className="matter-rail">
          <div>
            <div className="matter-rail-head"><BriefcaseBusiness size={16} className="text-[var(--accent)]" />{roleCopy.matters}</div>
            <div className="mt-3 flex gap-2">
              <input value={newTitle} onChange={(event) => setNewTitle(event.target.value)} placeholder="New matter title" className="field h-10 min-w-0 flex-1" />
              <button onClick={makeCase} aria-label="Create case" disabled={busy === "case" || newTitle.trim().length < 3} className="flex h-10 w-10 flex-none items-center justify-center rounded-xl bg-[var(--ink)] text-[var(--paper)] disabled:opacity-40">
                {busy === "case" ? <Loader2 size={15} className="animate-spin" /> : <Plus size={17} />}
              </button>
            </div>
            <div className="matter-list mt-3">
              {cases.map((item) => (
                <button key={item.id} onClick={() => setSelectedId(item.id)} aria-current={selectedId === item.id}>
                  <span className={`matter-dot ${item.status === "open" ? "" : "is-closed"}`} />
                  <span className="min-w-0 flex-1">
                    <span className="matter-name">{item.title}</span>
                    <span className="matter-meta">{item.status} / {item.role_type}</span>
                  </span>
                </button>
              ))}
              {!cases.length && (
                <div className="py-8 text-center">
                  <FolderPlus size={24} className="mx-auto text-[var(--ink-soft)]" />
                  <p className="mt-2 text-xs text-[var(--ink-soft)]">Create a matter to begin</p>
                </div>
              )}
            </div>
          </div>

          <nav aria-label="Matter tools" className="tool-rail">
            {tools.map((tool) => (
              <button key={tool.key} onClick={() => setView(tool.key)} aria-current={view === tool.key ? "page" : undefined}>
                <tool.icon size={16} />{tool.label}
              </button>
            ))}
          </nav>
        </aside>

        <div className="feature-view">
          <div className="feature-head">
            <div>
              <h3>{current.title}</h3>
              <p>{current.blurb}</p>
            </div>
            {(view === "deadlines" || view === "compliance" || view === "citations") && (
              <span className="feature-badge"><ShieldCheck size={13} />
                {view === "citations" ? "Official concordance" : "Read from the Sanhita"}
              </span>
            )}
          </div>

          {current.needsMatter && !selectedId ? (
            <div className="empty-matter">
              <FolderPlus size={26} className="text-[var(--ink-soft)]" />
              <p>Select a matter on the left, or create one, and this tool will work against it. Nothing here reads outside the matter you choose.</p>
            </div>
          ) : (
            <>
              {view === "agent" && (
                <div>
                  <textarea value={scenario} onChange={(event) => setScenario(event.target.value)} placeholder={isPolice ? "Enter the complainant account, dates, location, property or person description, witnesses and known circumstances…" : "Describe allegations, evidence, disputed facts, procedural history and the client position…"} className="field min-h-44 w-full resize-y leading-6" />
                  <button onClick={runProfessionalTool} disabled={busy === "tool" || scenario.trim().length < 40} className="button-primary mt-3">
                    {busy === "tool" ? <Loader2 size={15} className="animate-spin" /> : <Scale size={15} />}
                    {isPolice ? "Generate review draft" : "Run two-sided analysis"}
                  </button>
                  {draft && (
                    <div className="mt-6 rounded-xl border border-[var(--border)]">
                      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border)] bg-[var(--card)] px-4 py-3">
                        <p className="text-xs font-semibold">Draft version {draft.version} / {draft.status}</p>
                        <p className="text-[11px] text-[var(--state-warn-text)]">{draft.missing_fields.length ? `Missing: ${draft.missing_fields.join(", ")}` : "Required facts captured"}</p>
                      </div>
                      <pre className="max-h-[520px] overflow-auto whitespace-pre-wrap p-5 text-xs leading-6 text-[var(--ink)]">{draft.rendered_text}</pre>
                    </div>
                  )}
                  {analysis && (
                    <div className="mt-6">
                      <div className="rounded-xl bg-[var(--hover)] p-4 text-sm leading-6 text-[var(--ink)]">{analysis.summary}</div>
                      <div className="mt-3 grid gap-3 lg:grid-cols-2">
                        {analysis.points.map((point, index) => (
                          <article key={`${point.category}-${index}`} className="rounded-xl border border-[var(--border)] p-4">
                            <p className="text-[10px] font-semibold text-[var(--accent)]">{point.category.replaceAll("_", " ")} / {point.verification}</p>
                            <p className="mt-2 text-sm leading-6 text-[var(--ink)]">{point.point}</p>
                          </article>
                        ))}
                      </div>
                      <p className="mt-4 text-xs text-[var(--ink-soft)]">{analysis.disclaimer}</p>
                    </div>
                  )}
                </div>
              )}

              {view === "deadlines" && <InvestigationTimeline caseId={selectedId} />}
              {view === "compliance" && <ComplianceChecklist caseId={selectedId} />}
              {view === "citations" && <AuthorityCheck caseId={selectedId} />}

              {view === "search" && (
                <div>
                  <div className="inline-flex rounded-lg bg-[var(--hover)] p-1">
                    <button onClick={() => setSearchMode("case_specific")} className={`rounded-md px-3 py-1.5 text-xs font-medium ${searchMode === "case_specific" ? "bg-[var(--card)] text-[var(--ink)] shadow-sm" : "text-[var(--ink-soft)]"}`}>Selected matter</button>
                    <button onClick={() => setSearchMode("general")} className={`rounded-md px-3 py-1.5 text-xs font-medium ${searchMode === "general" ? "bg-[var(--card)] text-[var(--ink)] shadow-sm" : "text-[var(--ink-soft)]"}`}>All my matters</button>
                  </div>
                  <textarea value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} placeholder="Search legal authority and authorised evidence…" className="field mt-4 min-h-28 w-full resize-y leading-6" />
                  <button onClick={search} disabled={busy === "search" || !searchQuery.trim()} className="button-primary mt-3">
                    {busy === "search" ? <Loader2 size={15} className="animate-spin" /> : <FileSearch size={15} />}Search sources
                  </button>
                  <div className="mt-5 space-y-2">
                    {searchResults.map((hit) => (
                      <article key={`${hit.payload.collection_name}-${hit.point_id}`} className="rounded-xl border border-[var(--border)] p-3.5">
                        <div className="flex items-center justify-between gap-3">
                          <p className="truncate text-xs font-semibold text-[var(--accent)]">{String(hit.payload.title ?? "Private case evidence")}</p>
                          <span className="text-[10px] text-[var(--ink-soft)]">{Math.round(hit.reranker_score * 100)}% match</span>
                        </div>
                        <p className="mt-2 line-clamp-4 text-xs leading-5 text-[var(--ink-soft)]">{String(hit.payload.text ?? "")}</p>
                      </article>
                    ))}
                    {!searchResults.length && <p className="state-hint">No results yet. Searching a selected matter includes its private evidence; searching all matters covers only your own.</p>}
                  </div>
                </div>
              )}

              {view === "evidence" && (
                <div>
                  <label className="block text-xs font-medium text-[var(--ink)]">Evidence classification
                    <select value={docType} onChange={(event) => setDocType(event.target.value)} className="field mt-2">
                      {isPolice
                        ? <><option value="witness_statement">Witness statement</option><option value="fir">FIR / complaint</option><option value="forensic_report">Forensic report</option><option value="seizure_record">Seizure / chain-of-custody record</option><option value="order">Court order</option></>
                        : <><option value="client_statement">Client statement</option><option value="pleading">Pleading / petition</option><option value="opponent_filing">Opposing filing</option><option value="evidence_exhibit">Evidence exhibit</option><option value="order">Order / judgment</option></>}
                      <option value="other">Other evidence</option>
                    </select>
                  </label>
                  <label className="mt-4 flex min-h-40 cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-[var(--state-warn-line)] bg-[var(--hover)] px-4 text-center transition hover:bg-[var(--card)]">
                    <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--card)] text-[var(--accent)] shadow-sm">
                      {busy === "upload" ? <Loader2 size={19} className="animate-spin" /> : <UploadCloud size={19} />}
                    </div>
                    <p className="mt-3 text-sm font-medium text-[var(--ink)]">Choose evidence to upload</p>
                    <p className="mt-1 text-xs text-[var(--ink-soft)]">PDF or TXT / private to this matter</p>
                    <input type="file" accept="application/pdf,text/plain" className="hidden" disabled={busy === "upload"} onChange={(event) => upload(event.target.files?.[0])} />
                  </label>
                </div>
              )}

              {view === "documents" && <DocumentAnalyzerWorkspace caseId={selectedId} role={user.role} refreshToken={documentRefresh} />}
            </>
          )}
        </div>
      </div>
    </section>
  );
}
