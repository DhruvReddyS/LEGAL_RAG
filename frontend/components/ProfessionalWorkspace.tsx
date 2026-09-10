"use client";

import { AlertTriangle, ArrowRight, BriefcaseBusiness, CalendarClock, Check, ClipboardCheck, ClipboardCopy, ScanText, CheckCircle2, Download, FilePlus2, FileSearch, FileText, FolderPlus, Loader2, MessageSquare, MessageSquarePlus, Pencil, Plus, Scale, ScanSearch, ShieldCheck, UploadCloud } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { AuthorityCheck } from "@/components/AuthorityCheck";
import { ComplianceChecklist } from "@/components/ComplianceChecklist";
import { InvestigationTimeline } from "@/components/InvestigationTimeline";
import { ApiError, analyseDefence, createCase, draftFir, getInvestigationTimeline, indexCaseEvidence, listCases, listGeneratedDocuments, listIndexedCaseDocuments, readGeneratedDocument, scopedSearch, updateCase, uploadCaseEvidence } from "@/lib/api";
import type { CaseDocumentSummary, DefenceAnalysisResponse, FIRDraftResponse, GeneratedDocumentSummary, InvestigationTimeline as InvestigationTimelineData, LegalCase, RetrievalHit, User } from "@/lib/types";
import DocumentAnalyzerWorkspace from "@/components/DocumentAnalyzerWorkspace";

function errorText(error: unknown): string { return error instanceof ApiError ? error.message : "The operation failed. Check the backend and try again."; }

export type MatterChat = { id: string; sessionId: string | null; title: string; caseId: string | null; updatedAt: number };

export default function ProfessionalWorkspace({
  user,
  chats = [],
  onCasesChange,
  onNewMatterChat,
  onOpenMatterChat,
  requestedView = null,
}: {
  user: User;
  chats?: MatterChat[];
  onCasesChange?: (cases: LegalCase[]) => void;
  onNewMatterChat?: (caseId: string) => void;
  onOpenMatterChat?: (chatId: string) => void;
  requestedView?: { view: string; nonce: number } | null;
}) {
  const isPolice = user.role === "police";
  const roleCopy = isPolice ? {
    eyebrow: "Police investigation work",
    matters: "Your investigations",
    description: "Lawful procedure, investigation records and ownership-isolated police evidence.",
    intake: "Investigation evidence intake",
    search: "Procedure & evidence search",
  } : {
    eyebrow: "Advocate case work",
    matters: "Your cases",
    description: "Two-sided authority research and ownership-isolated client evidence.",
    intake: "Client evidence intake",
    search: "Authority & case search",
  };
  const [cases, setCases] = useState<LegalCase[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [newTitle, setNewTitle] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [failed, setFailed] = useState(false);
  const [searchMode, setSearchMode] = useState<"general" | "case_specific">("case_specific");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<RetrievalHit[]>([]);
  const [docType, setDocType] = useState(isPolice ? "witness_statement" : "client_statement");
  const [scenario, setScenario] = useState("");
  const [draft, setDraft] = useState<FIRDraftResponse | null>(null);
  const [analysis, setAnalysis] = useState<DefenceAnalysisResponse | null>(null);
  const [documentRefresh, setDocumentRefresh] = useState(0);
  const [view, setView] = useState<ViewKey>("casefile");
  const fail = (message: string) => { setFailed(true); setNotice(message); };
  const selected = useMemo(() => cases.find((item) => item.id === selectedId), [cases, selectedId]);
  // A sidebar link opens the feature it names. Unknown names are ignored
  // rather than blanking the working area.
  useEffect(() => {
    if (!requestedView) return;
    if (tools.some((tool) => tool.key === requestedView.view)) setView(requestedView.view as ViewKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestedView?.nonce, requestedView?.view]);
  const matterChats = useMemo(
    () => chats.filter((chat) => chat.caseId === selectedId).sort((a, b) => b.updatedAt - a.updatedAt),
    [chats, selectedId],
  );
  const [files, setFiles] = useState<CaseDocumentSummary[] | null>(null);
  const [drafts, setDrafts] = useState<GeneratedDocumentSummary[] | null>(null);
  useEffect(() => {
    if (!selectedId) { setFiles(null); setDrafts(null); return; }
    let cancelled = false;
    // Null rather than an empty list while unknown: "nothing filed" and
    // "could not ask" must not read the same on a case record.
    setFiles(null); setDrafts(null);
    listIndexedCaseDocuments(selectedId).then((r) => { if (!cancelled) setFiles(r.documents); }).catch(() => { if (!cancelled) setFiles(null); });
    listGeneratedDocuments(selectedId).then((r) => { if (!cancelled) setDrafts(r.documents); }).catch(() => { if (!cancelled) setDrafts(null); });
    return () => { cancelled = true; };
  }, [selectedId, documentRefresh, draft, analysis]);
  const [timeline, setTimeline] = useState<InvestigationTimelineData | "none" | null>(null);
  useEffect(() => {
    if (!selectedId || !isPolice) { setTimeline(null); return; }
    let cancelled = false;
    setTimeline(null);
    getInvestigationTimeline(selectedId)
      .then((r) => { if (!cancelled) setTimeline(r); })
      .catch((error) => { if (!cancelled) setTimeline(error instanceof ApiError && error.status === 404 ? "none" : null); });
    return () => { cancelled = true; };
  }, [selectedId, isPolice, documentRefresh]);
  const computed = timeline === "none" ? null : timeline;
  const nextDeadline = useMemo(() => {
    const dated = (computed?.deadlines ?? []).filter((item) => item.due_at && !item.is_breached);
    return dated.sort((a, b) => Date.parse(a.due_at!) - Date.parse(b.due_at!))[0] ?? null;
  }, [computed]);
  const [caseFilter, setCaseFilter] = useState("");
  const visibleCases = useMemo(() => {
    const needle = caseFilter.trim().toLowerCase();
    // A closed case stays reachable by name, but does not crowd the rail.
    const base = needle ? cases : cases.filter((item) => item.status === "open" || item.id === selectedId);
    return needle ? base.filter((item) => item.title.toLowerCase().includes(needle)) : base;
  }, [cases, caseFilter, selectedId]);
  const hiddenCount = cases.length - visibleCases.length;
  const [renaming, setRenaming] = useState(false);
  const [renameDraft, setRenameDraft] = useState("");
  const applyCaseChange = async (changes: { title?: string; status?: "open" | "closed" | "archived" }) => {
    if (!selectedId) return;
    setBusy("case-edit"); setNotice(""); setFailed(false);
    try {
      const updated = await updateCase(selectedId, changes);
      setCases((current) => {
        const next = current.map((item) => (item.id === updated.id ? updated : item));
        onCasesChange?.(next);
        return next;
      });
      setNotice(changes.status ? `Case marked ${changes.status}.` : "Case renamed.");
    } catch (error) { fail(errorText(error)); } finally { setBusy(null); setRenaming(false); }
  };
  const [copied, setCopied] = useState(false);
  const draftText = (item: FIRDraftResponse) =>
    // The disclaimer travels with the text. A draft pasted into a case
    // diary without it reads as a finished document, which it is not.
    `${item.rendered_text}\n\n---\n${item.disclaimer}`;
  const copyDraft = async (item: FIRDraftResponse) => {
    try {
      await navigator.clipboard.writeText(draftText(item));
      setCopied(true); window.setTimeout(() => setCopied(false), 2000);
    } catch { fail("The browser refused clipboard access. Select the text and copy it instead."); }
  };
  const downloadDraft = (item: FIRDraftResponse) => {
    const blob = new Blob([draftText(item)], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${item.doc_type}-v${item.version}-${(selected?.title ?? "case").replace(/[^a-z0-9]+/gi, "-").toLowerCase()}.txt`;
    link.click();
    URL.revokeObjectURL(url);
  };
  // Everything on screen belongs to one case. Selecting another one has to
  // clear it: a draft, an analysis or a search result left standing under a
  // different case's name is read as that case's material.
  useEffect(() => {
    setDraft(null);
    setAnalysis(null);
    setScenario("");
    setSearchResults([]);
    setNotice("");
    setFailed(false);
    setRenaming(false);
  }, [selectedId]);
  const openDraft = async (documentId: string) => {
    if (!selectedId) return;
    setBusy("draft"); setNotice(""); setFailed(false);
    // Read back, never re-drafted: a reviewed draft must not change under
    // the officer who reviewed it.
    try { setDraft(await readGeneratedDocument(selectedId, documentId)); setView("agent"); }
    catch (error) { fail(errorText(error)); } finally { setBusy(null); }
  };
  const docLabel = (type: string) => type.split(/[_-]/).map((word) => word.toUpperCase() === "FIR" ? "FIR" : word).join(" ").replace(/^./, (c) => c.toUpperCase());

  useEffect(() => { listCases().then((response) => { setCases(response.cases); setSelectedId(response.cases[0]?.id ?? ""); onCasesChange?.(response.cases); }).catch((error) => fail(errorText(error)));
  // Loaded once per mount. onCasesChange is a setter and is deliberately not
  // a dependency: including it would refetch on every parent render.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const makeCase = async () => {
    if (newTitle.trim().length < 3) return; setBusy("case"); setNotice(""); setFailed(false);
    try { const created = await createCase(newTitle.trim()); setCases((current) => { const next = [created, ...current]; onCasesChange?.(next); return next; }); setSelectedId(created.id); setNewTitle(""); setView("casefile"); setNotice("Case created. Only you can read the files you add to it."); }
    catch (error) { fail(errorText(error)); } finally { setBusy(null); }
  };
  const search = async () => {
    if (!searchQuery.trim() || (searchMode === "case_specific" && !selectedId)) return; setBusy("search"); setNotice(""); setFailed(false);
    try { const response = await scopedSearch(searchQuery.trim(), searchMode, selectedId); setSearchResults(response.results); setNotice(`Retrieved ${response.results.length} authorised public and private results.`); }
    catch (error) { fail(errorText(error)); } finally { setBusy(null); }
  };
  const upload = async (file?: File) => {
    if (!file || !selectedId) return; setBusy("upload"); setNotice(""); setFailed(false);
    try { const stored = await uploadCaseEvidence(selectedId, file); const indexed = await indexCaseEvidence(selectedId, stored.id, docType); setDocumentRefresh((value) => value + 1); setNotice(`Indexed ${file.name}: ${indexed.pages} page(s), ${indexed.chunks} private passage(s). It is ready in Document Analyzer.`); }
    catch (error) { fail(errorText(error)); } finally { setBusy(null); }
  };
  const runProfessionalTool = async () => {
    if (!selectedId || scenario.trim().length < 40) return; setBusy("tool"); setNotice(""); setFailed(false); setDraft(null); setAnalysis(null);
    try {
      if (user.role === "police") { const result = await draftFir(selectedId, scenario.trim()); setDraft(result); setNotice(`Created immutable FIR draft version ${result.version}.`); }
      else { const result = await analyseDefence(selectedId, scenario.trim()); setAnalysis(result); setNotice(`Verified ${result.points.length} strategy point(s); rejected ${result.rejected_point_count}.`); }
    } catch (error) { fail(errorText(error)); } finally { setBusy(null); }
  };


type ViewKey = "casefile" | "agent" | "deadlines" | "compliance" | "citations" | "search" | "evidence" | "documents";

  const tools: { key: ViewKey; label: string; icon: typeof Scale; title: string; blurb: string; needsMatter: boolean }[] = [
    {
      key: "casefile",
      label: "Case file",
      icon: BriefcaseBusiness,
      title: isPolice ? "Investigation file" : "Case file",
      blurb: "What is on record for this case, and the chats allowed to read it. Every other tool here works only on the case selected on the left.",
      needsMatter: true,
    },
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
      blurb: "Search the law, and the files in the case you have selected. Results never cross into another case or another role.",
      needsMatter: false,
    },
    {
      key: "evidence",
      label: "Add evidence",
      icon: UploadCloud,
      title: roleCopy.intake,
      blurb: "A PDF or UTF-8 statement. Scanned pages are read by OCR and indexed for this case alone.",
      needsMatter: true,
    },
    {
      key: "documents",
      label: "Review documents",
      icon: ScanSearch,
      title: "Document analyzer",
      blurb: "Read what was indexed for this case, with the passage, its pages and its current-law status.",
      needsMatter: true,
    },
  ];
  const current = tools.find((tool) => tool.key === view) ?? tools[0];
  const workflow = isPolice
    ? [
        { label: "Open an investigation", detail: "Select or create the case record.", target: "casefile" as ViewKey },
        { label: "Build the record", detail: "Add evidence and record dates.", target: "evidence" as ViewKey },
        { label: "Review and act", detail: "Draft, verify and check compliance.", target: "agent" as ViewKey },
      ]
    : [
        { label: "Open a case", detail: "Select or create the client matter.", target: "casefile" as ViewKey },
        { label: "Build the record", detail: "Add evidence and find authority.", target: "evidence" as ViewKey },
        { label: "Develop strategy", detail: "Analyse both sides and verify citations.", target: "agent" as ViewKey },
      ];

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

      <div className="professional-path" aria-label={`${isPolice ? "Investigation" : "Case"} workflow`}>
        <div className="professional-path-intro">
          <span>Recommended path</span>
          <strong>Move from facts to a reviewable result.</strong>
        </div>
        <div className="professional-path-steps">
          {workflow.map((step, index) => (
            <button key={step.target} onClick={() => setView(step.target)}>
              <b>{String(index + 1).padStart(2, "0")}</b>
              <span><strong>{step.label}</strong><small>{step.detail}</small></span>
              {index < workflow.length - 1 && <ArrowRight size={14} aria-hidden="true" />}
            </button>
          ))}
        </div>
      </div>

      {notice && (
        <div role={failed ? "alert" : "status"} className={`mb-5 flex items-center gap-2 rounded-xl px-4 py-3 text-sm ${failed ? "border border-[var(--state-bad-line)] bg-[var(--state-bad-bg)] text-[var(--state-bad-text)]" : "border border-[var(--state-ok-line)] bg-[var(--state-ok-bg)] text-[var(--state-ok-text)]"}`}>
          {failed ? <AlertTriangle size={16} /> : <CheckCircle2 size={16} />}{notice}
        </div>
      )}

      <div className="matter-shell">
        <aside className="matter-rail">
          <div>
            <div className="matter-rail-head"><BriefcaseBusiness size={16} className="text-[var(--accent)]" />{roleCopy.matters}</div>
            <div className="mt-3 flex gap-2">
              <input value={newTitle} onChange={(event) => setNewTitle(event.target.value)} placeholder={isPolice ? "New investigation title" : "New case title"} className="field h-10 min-w-0 flex-1" />
              <button onClick={makeCase} aria-label="Create case" disabled={busy === "case" || newTitle.trim().length < 3} className="flex h-10 w-10 flex-none items-center justify-center rounded-xl bg-[var(--ink)] text-[var(--paper)] disabled:opacity-40">
                {busy === "case" ? <Loader2 size={15} className="animate-spin" /> : <Plus size={17} />}
              </button>
            </div>
            {cases.length > 6 && (
              <input value={caseFilter} onChange={(event) => setCaseFilter(event.target.value)} placeholder="Filter by name" aria-label="Filter cases by name" className="field mt-2 h-9 w-full text-xs" />
            )}
            <div className="matter-list mt-3">
              {visibleCases.map((item) => (
                <button key={item.id} onClick={() => setSelectedId(item.id)} aria-current={selectedId === item.id}>
                  <span className={`matter-dot ${item.status === "open" ? "" : "is-closed"}`} />
                  <span className="min-w-0 flex-1">
                    <span className="matter-name">{item.title}</span>
                    <span className="matter-meta">{item.status} / {item.role_type}</span>
                  </span>
                </button>
              ))}
              {!!cases.length && !visibleCases.length && (
                <p className="py-6 text-center text-xs text-[var(--ink-soft)]">No case matches that name.</p>
              )}
              {!!hiddenCount && !caseFilter.trim() && (
                <p className="pt-2 text-center text-[11px] text-[var(--ink-soft)]">{hiddenCount} closed or archived. Type a name to find one.</p>
              )}
              {!cases.length && (
                <div className="py-8 text-center">
                  <FolderPlus size={24} className="mx-auto text-[var(--ink-soft)]" />
                  <p className="mt-2 text-xs text-[var(--ink-soft)]">Start a case to begin</p>
                </div>
              )}
            </div>
          </div>

          <nav aria-label="Case tools" className="tool-rail">
            {tools.map((tool) => (
              <button key={tool.key} onClick={() => setView(tool.key)} aria-current={view === tool.key ? "page" : undefined}>
                <tool.icon size={16} />
                <span><strong>{tool.label}</strong><small>{tool.title}</small></span>
              </button>
            ))}
          </nav>
        </aside>

        <div className="feature-view">
          <div className="feature-head">
            <div>
              <span className="feature-location">{selected ? selected.title : "No case selected"} / {current.label}</span>
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
            <div className="empty-case">
              <FolderPlus size={26} className="text-[var(--ink-soft)]" />
              <p>Pick a case on the left, or start one, and this tool works only on that case. Nothing here reads any other case.</p>
            </div>
          ) : (
            <>
              {view === "casefile" && selected && (
                <div className="case-file">
                  <dl className="case-facts">
                    <div className="case-fact-wide"><dt>Case</dt><dd>
                      {renaming ? (
                        <form className="case-rename" onSubmit={(event) => { event.preventDefault(); if (renameDraft.trim().length >= 3) void applyCaseChange({ title: renameDraft.trim() }); }}>
                          <input autoFocus aria-label="Case title" value={renameDraft} maxLength={255} onChange={(event) => setRenameDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Escape") setRenaming(false); }} className="field h-9" />
                          <button type="submit" disabled={busy === "case-edit" || renameDraft.trim().length < 3} aria-label="Save case title"><Check size={15} /></button>
                        </form>
                      ) : (
                        <span className="case-title-row">{selected.title}
                          <button onClick={() => { setRenameDraft(selected.title); setRenaming(true); }} aria-label="Rename case" title="Rename case"><Pencil size={13} /></button>
                        </span>
                      )}
                    </dd></div>
                    <div><dt>Status</dt><dd>
                      <select aria-label="Case status" className="case-status" value={selected.status} disabled={busy === "case-edit"} onChange={(event) => void applyCaseChange({ status: event.target.value as "open" | "closed" | "archived" })}>
                        <option value="open">Open</option>
                        <option value="closed">Closed</option>
                        <option value="archived">Archived</option>
                      </select>
                    </dd></div>
                    <div><dt>Opened</dt><dd>{new Date(selected.created_at).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}</dd></div>
                    <div><dt>Files</dt><dd>{files === null ? "—" : files.length.toLocaleString()}</dd></div>
                    <div><dt>{isPolice ? "Drafts" : "Analyses"}</dt><dd>{drafts === null ? "—" : drafts.length.toLocaleString()}</dd></div>
                    <div><dt>Searchable passages</dt><dd>{files === null ? "—" : files.reduce((total, item) => total + item.chunk_count, 0).toLocaleString()}</dd></div>
                  </dl>

                  <section className="case-block">
                    <div className="case-block-head">
                      <div>
                        <h4>Chats about this case</h4>
                        <p>These read the law and the files uploaded to this case. A law-only chat reads no case files at all.</p>
                      </div>
                      <button className="button-primary" onClick={() => onNewMatterChat?.(selected.id)}>
                        <MessageSquarePlus size={15} />New chat about this case
                      </button>
                    </div>
                    {matterChats.length ? (
                      <ul className="case-chats">
                        {matterChats.map((chat) => (
                          <li key={chat.id}>
                            <button onClick={() => onOpenMatterChat?.(chat.id)}>
                              <MessageSquare size={14} />
                              <span className="min-w-0 flex-1 truncate">{chat.title}</span>
                              <span className="case-chat-when">{chat.updatedAt ? new Date(chat.updatedAt).toLocaleDateString() : "—"}</span>
                            </button>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="case-empty">No chat has been opened about this case yet.</p>
                    )}
                  </section>

                  {isPolice && (
                    <section className="case-block">
                      <div className="case-block-head">
                        <div>
                          <h4>Where this investigation stands</h4>
                          <p>Computed from the dates recorded for this case by date arithmetic. A date nobody has entered produces a stated unknown, not an estimate.</p>
                        </div>
                        <button className="button-primary" onClick={() => setView("deadlines")}>
                          <CalendarClock size={15} />Record dates
                        </button>
                      </div>
                      {computed?.breached.length ? (
                        <p className="case-alert">{computed.breached.length} time limit{computed.breached.length === 1 ? " has" : "s have"} passed. Open the deadlines page for the provision and the consequence.</p>
                      ) : nextDeadline ? (
                        <p className="case-line"><strong>{nextDeadline.obligation}</strong> &mdash; due {new Date(nextDeadline.due_at!).toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })} under {nextDeadline.provision}.</p>
                      ) : (
                        <p className="case-empty">{
                          timeline === "none" ? "No dates recorded for this case yet, so no BNSS period can be computed. Record the arrest, remand and information dates to start the clock."
                          : timeline === null ? "The timeline could not be read."
                          : `No deadline can be computed yet: ${timeline.undetermined.length} of ${timeline.deadlines.length} depend on dates that are not recorded.`
                        }</p>
                      )}
                    </section>
                  )}

                  <section className="case-block">
                    <div className="case-block-head">
                      <div>
                        <h4>{isPolice ? "FIRs drafted in this case" : "Analyses in this case"}</h4>
                        <p>{isPolice ? "Every draft is kept as its own version. Opening one shows the text as it was written, with the provisions it cited." : "Each analysis is kept with the authorities it was allowed to rely on."}</p>
                      </div>
                      <button className="button-primary" onClick={() => { setDraft(null); setAnalysis(null); setView("agent"); }}>
                        <FilePlus2 size={15} />{isPolice ? "New FIR draft" : "New analysis"}
                      </button>
                    </div>
                    {drafts?.length ? (
                      <ul className="case-chats">
                        {drafts.map((item) => (
                          <li key={item.id}>
                            <button onClick={() => openDraft(item.id)} disabled={busy === "draft"}>
                              <FileText size={14} />
                              <span className="min-w-0 flex-1 truncate">{docLabel(item.doc_type)} &middot; version {item.version}</span>
                              {item.missing_field_count > 0 && <span className="case-flag">{item.missing_field_count} field{item.missing_field_count === 1 ? "" : "s"} missing</span>}
                              <span className="case-chat-when">{new Date(item.created_at).toLocaleDateString()}</span>
                            </button>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="case-empty">{drafts === null ? "The drafting history could not be read." : "Nothing has been drafted in this case yet."}</p>
                    )}
                  </section>

                  <section className="case-block">
                    <div className="case-block-head">
                      <div>
                        <h4>Files in this case</h4>
                        <p>Uploaded evidence, indexed so a chat in this case can quote it. No other case, and nobody else, can read them.</p>
                      </div>
                      <button className="button-primary" onClick={() => setView("evidence")}>
                        <UploadCloud size={15} />Add a file
                      </button>
                    </div>
                    {files?.length ? (
                      <ul className="case-chats">
                        {files.map((item) => (
                          <li key={item.document_id}>
                            <button onClick={() => setView("documents")}>
                              <FileSearch size={14} />
                              <span className="min-w-0 flex-1 truncate">{item.filename}</span>
                              <span className="case-chat-when">{item.page_count} pp &middot; {item.chunk_count} passages</span>
                            </button>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="case-empty">{files === null ? "The file list could not be read." : "No file has been added to this case yet."}</p>
                    )}
                  </section>

                  <section className="case-block">
                    <div className="case-block-head">
                      <div>
                        <h4>Where to go next</h4>
                        <p>Each tool opens as its own page and works only on this case.</p>
                      </div>
                    </div>
                    <div className="case-next">
                      {tools.filter((tool) => tool.key !== "casefile").map((tool) => (
                        <button key={tool.key} onClick={() => setView(tool.key)}>
                          <tool.icon size={15} />
                          <span><strong>{tool.label}</strong><small>{tool.title}</small></span>
                        </button>
                      ))}
                    </div>
                  </section>
                </div>
              )}

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
                        <div className="flex items-center gap-3">
                          <p className="text-[11px] text-[var(--state-warn-text)]">{draft.missing_fields.length ? `Missing: ${draft.missing_fields.join(", ")}` : "Required facts captured"}</p>
                          <button className="draft-action" onClick={() => void copyDraft(draft)}>{copied ? <Check size={13} /> : <ClipboardCopy size={13} />}{copied ? "Copied" : "Copy"}</button>
                          <button className="draft-action" onClick={() => downloadDraft(draft)}><Download size={13} />Save</button>
                        </div>
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
                    <button onClick={() => setSearchMode("case_specific")} className={`rounded-md px-3 py-1.5 text-xs font-medium ${searchMode === "case_specific" ? "bg-[var(--card)] text-[var(--ink)] shadow-sm" : "text-[var(--ink-soft)]"}`}>This case</button>
                    <button onClick={() => setSearchMode("general")} className={`rounded-md px-3 py-1.5 text-xs font-medium ${searchMode === "general" ? "bg-[var(--card)] text-[var(--ink)] shadow-sm" : "text-[var(--ink-soft)]"}`}>All my cases</button>
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
                    {!searchResults.length && <p className="state-hint">No results yet. Searching this case also reads the files in it; searching all your cases reads the law and nothing private.</p>}
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
                    <p className="mt-1 text-xs text-[var(--ink-soft)]">PDF or TXT / stays inside this case</p>
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
