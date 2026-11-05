"use client";

import { ArrowLeft, ArrowRight, Check, CheckCircle2, Circle, Fingerprint, BriefcaseBusiness, MessageSquare, Pencil, X } from "lucide-react";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { ApiError, listGeneratedDocuments, listIndexedCaseDocuments, updateCase } from "@/lib/api";
import { caseReference, plural, shortDate, sortDue } from "@/lib/pro-presentation";
import type { CaseDocumentSummary, DefenceAnalysisResponse, GeneratedDocumentSummary, LegalCase } from "@/lib/types";
import { Card, DueRow, EmptyState, ErrorState, ProLink, RowsLoading, usePro } from "./context";
import type { ChatView } from "./ProApp";
import { caseTabs, type CaseTab, type CaseTool, type CaseToolContext } from "./case/tabs";

const AdvocateCaseFile = dynamic(() => import("@/components/advocate/DefenceAnalysisResult").then((m) => m.AdvocateCaseFile), { loading: () => <RowsLoading label="Loading" /> });

function CaseHeader({ legalCase, tabs, activeTab }: { legalCase: LegalCase; tabs: CaseTab[]; activeTab: string }) {
  const { isPolice, nounPlural, noun, replaceCase } = usePro();
  const [renaming, setRenaming] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  const change = async (changes: { title?: string; status?: "open" | "closed" | "archived" }) => {
    setBusy(true); setFailure("");
    try { replaceCase(await updateCase(legalCase.id, changes)); setRenaming(false); }
    catch (error) { setFailure(error instanceof ApiError ? error.message : "The change could not be saved. Try again."); }
    finally { setBusy(false); }
  };
  const Mark = isPolice ? Fingerprint : BriefcaseBusiness;
  return (
    <header className="pro-case-head">
      <div className="pro-case-top">
        <ProLink to={{ section: "cases" }} className="pro-back"><ArrowLeft size={14} aria-hidden="true" />{nounPlural}</ProLink>
        <span className="pro-case-role"><Mark size={13} aria-hidden="true" />{isPolice ? "Police investigation" : "Advocate case"}</span>
      </div>
      <div className="pro-case-title">
        {renaming ? (
          <form className="pro-rename" onSubmit={(event) => { event.preventDefault(); if (draft.trim().length >= 3) void change({ title: draft.trim() }); }}>
            <input autoFocus aria-label={`${noun} title`} className="field" value={draft} maxLength={255} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Escape") setRenaming(false); }} />
            <button type="submit" className="icon-button" aria-label="Save title" disabled={busy || draft.trim().length < 3}><Check size={16} /></button>
            <button type="button" className="icon-button" aria-label="Cancel renaming" onClick={() => setRenaming(false)}><X size={16} /></button>
          </form>
        ) : (
          <>
            <h1>{legalCase.title}</h1>
            <button type="button" className="icon-button" aria-label={`Rename this ${noun}`} title="Rename" onClick={() => { setDraft(legalCase.title); setRenaming(true); }}><Pencil size={14} /></button>
          </>
        )}
        <div className="pro-case-facts">
          <span>Ref. {caseReference(legalCase.id)}</span>
          <label className={`pro-status-select is-${legalCase.status}`}>
            <span className="sr-only">Status of this {noun}</span>
            <select value={legalCase.status} disabled={busy} onChange={(event) => void change({ status: event.target.value as "open" | "closed" | "archived" })}>
              <option value="open">Open</option>
              <option value="closed">Closed</option>
              <option value="archived">Archived</option>
            </select>
          </label>
        </div>
      </div>
      {failure && <p className="pro-form-error" role="alert">{failure}</p>}
      <nav className="pro-tabs" aria-label="Case sections">
        {tabs.map((tab) => (
          <ProLink key={tab.key} to={{ section: "case", caseId: legalCase.id, tab: tab.key === "overview" ? undefined : tab.key }} current={activeTab === tab.key}>
            <tab.icon size={14} aria-hidden="true" />{tab.label}
          </ProLink>
        ))}
      </nav>
    </header>
  );
}

function Overview({ legalCase, ctx }: { legalCase: LegalCase; ctx: CaseToolContext & { onOpenAnalysis: (analysis: DefenceAnalysisResponse) => void } }) {
  const { isPolice, due, dueState, chats, openChat, noun } = usePro();
  const [files, setFiles] = useState<CaseDocumentSummary[] | null>(null);
  const [drafts, setDrafts] = useState<GeneratedDocumentSummary[] | null>(null);
  const { caseId, refresh, go } = ctx;
  useEffect(() => {
    let cancelled = false;
    // Null rather than an empty list while unknown: "nothing filed" and "could not ask" must not read the same.
    listIndexedCaseDocuments(caseId).then((r) => { if (!cancelled) setFiles(r.documents); }).catch(() => { if (!cancelled) setFiles(null); });
    if (isPolice) listGeneratedDocuments(caseId).then((r) => { if (!cancelled) setDrafts(r.documents); }).catch(() => { if (!cancelled) setDrafts(null); });
    return () => { cancelled = true; };
  }, [caseId, refresh, isPolice]);
  const mine = useMemo(() => sortDue(due.filter((item) => item.caseId === caseId)), [due, caseId]);
  const open = mine.filter((item) => item.bucket !== "done");
  const caseChats = useMemo(() => chats.filter((chat) => chat.caseId === caseId).sort((a, b) => b.updatedAt - a.updatedAt).slice(0, 4), [chats, caseId]);
  const datesTab = isPolice ? "deadlines" : "dates";
  const steps: { label: string; detail: string; done: boolean; tab: string; tool?: string }[] = isPolice
    ? [
        { label: "Record the key dates", detail: "Time limits are computed from them.", done: mine.length > 0, tab: datesTab },
        { label: "Add files", detail: "Statements, reports and records.", done: (files?.length ?? 0) > 0, tab: "files" },
        { label: "Start a draft", detail: "From the facts known so far.", done: (drafts?.length ?? 0) > 0, tab: "drafts" },
      ]
    : [
        { label: "Add hearings and limitation dates", detail: "So nothing falls due unseen.", done: mine.length > 0, tab: datesTab },
        { label: "Add the client's files", detail: "Statements, pleadings and orders.", done: (files?.length ?? 0) > 0, tab: "files" },
        { label: "Work on the argument", detail: "Analyse both sides of the case.", done: false, tab: "strategy" },
      ];
  const pending = steps.filter((step) => !step.done);
  return (
    <div className="pro-overview">
      <div className="pro-overview-main">
        {pending.length > 0 && (
          <Card title="Next steps" id="ov-steps">
            <ol className="pro-steps">
              {steps.map((step) => (
                <li key={step.label} className={step.done ? "is-done" : ""}>
                  {step.done ? <CheckCircle2 size={16} aria-label="Done" /> : <Circle size={16} aria-hidden="true" />}
                  <ProLink to={{ section: "case", caseId, tab: step.tab, tool: step.tool }}>
                    <strong>{step.label}</strong><span>{step.detail}</span>
                  </ProLink>
                </li>
              ))}
            </ol>
          </Card>
        )}
        <Card
          title={isPolice ? "Where this investigation stands" : "Dates in this case"}
          id="ov-due"
          action={<ProLink to={{ section: "case", caseId, tab: datesTab }} className="pro-card-link">{isPolice ? "Open deadlines" : "Open dates"}<ArrowRight size={13} aria-hidden="true" /></ProLink>}
        >
          {dueState === "loading" && <RowsLoading label="Reading what is due" rows={2} />}
          {dueState === "failed" && <p className="pro-quiet">What is due could not be read just now.</p>}
          {dueState === "ready" && (open.length
            ? <ul className="pro-rows">{open.slice(0, 5).map((item) => <DueRow key={item.id} item={item} showCase={false} to={{ section: "case", caseId, tab: datesTab }} />)}</ul>
            : <p className="pro-quiet">{isPolice ? "No time limit can be computed yet. Record the dates of this investigation to see them. That does not mean none applies." : "No date is recorded for this case yet."}</p>)}
        </Card>
        {!isPolice && (
          <AdvocateCaseFile
            caseId={caseId}
            refreshToken={refresh}
            onOpenAnalysis={ctx.onOpenAnalysis}
            onNewAnalysis={() => go("strategy", "defence")}
            onOpenDesk={() => go("strategy")}
          />
        )}
      </div>
      <div className="pro-overview-side">
        <Card title="On record" id="ov-record">
          <dl className="pro-facts">
            <div><dt>Opened</dt><dd>{shortDate(legalCase.created_at)}</dd></div>
            <div><dt>Files</dt><dd>{files === null ? "—" : files.length.toLocaleString()}</dd></div>
            <div><dt>Searchable passages</dt><dd>{files === null ? "—" : files.reduce((total, item) => total + item.chunk_count, 0).toLocaleString()}</dd></div>
            {isPolice && <div><dt>FIR drafts</dt><dd>{drafts === null ? "—" : drafts.length.toLocaleString()}</dd></div>}
          </dl>
        </Card>
        <Card title={`Chats about this ${noun}`} id="ov-chats" action={<ProLink to={{ section: "case", caseId, tab: "ask" }} className="pro-card-link">Ask<ArrowRight size={13} aria-hidden="true" /></ProLink>}>
          {caseChats.length ? (
            <ul className="pro-rows">
              {caseChats.map((chat) => (
                <li key={chat.id}>
                  <button type="button" className="pro-activity" onClick={() => openChat(chat.id)}>
                    <MessageSquare size={14} aria-hidden="true" className="flex-none" />
                    <span className="pro-due-main"><strong>{chat.title}</strong></span>
                    <time>{shortDate(chat.updatedAt)}</time>
                  </button>
                </li>
              ))}
            </ul>
          ) : <p className="pro-quiet">Ask a question here and it can read the law and the files in this {noun}, and no other.</p>}
        </Card>
      </div>
    </div>
  );
}

function ToolList({ caseId, tab, active }: { caseId: string; tab: CaseTab; active: string }) {
  let lastGroup: string | undefined;
  return (
    <nav className="pro-toollist" aria-label={`${tab.label} tools`}>
      {tab.tools.map((tool) => {
        const heading = tool.group && tool.group !== lastGroup ? tool.group : null;
        lastGroup = tool.group;
        return (
          <span key={tool.key} className="contents">
            {heading && <span className="pro-toollist-group">{heading}</span>}
            <ProLink to={{ section: "case", caseId, tab: tab.key, tool: tool.key }} current={active === tool.key}>{tool.label}</ProLink>
          </span>
        );
      })}
    </nav>
  );
}

function ToolPane({ tool, ctx, hidden }: { tool: CaseTool; ctx: CaseToolContext; hidden: boolean }) {
  return (
    <section hidden={hidden} className="pro-tool" aria-label={tool.title}>
      <div className="pro-tool-head">
        <h2>{tool.title}</h2>
        <p>{tool.blurb}</p>
      </div>
      {tool.render(ctx)}
    </section>
  );
}

/**
 * One case and only that case. The shell mounts this under a key of the case id, so
 * opening another case replaces everything here, and every tool below gets the same id.
 * A tool stays mounted once visited, so moving between tabs keeps what was typed.
 */
export default function CasePage({ caseId, active, chatView }: { caseId: string; active: boolean; chatView: ChatView }) {
  const { user, isPolice, cases, casesState, reloadCases, reloadDue, route, navigate, noun, nounPlural } = usePro();
  const legalCase = cases.find((item) => item.id === caseId);
  const tabs = useMemo(() => caseTabs(isPolice), [isPolice]);
  const here = active && route.caseId === caseId;
  const [lastPlace, setLastPlace] = useState<{ tab?: string; tool?: string }>({});
  useEffect(() => { if (here) setLastPlace({ tab: route.tab, tool: route.tool }); }, [here, route.tab, route.tool]);
  const place = here ? route : lastPlace;
  const tab = tabs.find((item) => item.key === place.tab) ?? tabs[0];
  const tool = tab.tools.find((item) => item.key === place.tool) ?? tab.tools[0];

  const [visited, setVisited] = useState<Set<string>>(new Set());
  const paneKey = tool ? `${tab.key}/${tool.key}` : "";
  useEffect(() => {
    if (!paneKey) return;
    setVisited((current) => (current.has(paneKey) ? current : new Set(current).add(paneKey)));
  }, [paneKey]);

  const [refresh, setRefresh] = useState(0);
  const [openedAnalysis, setOpenedAnalysis] = useState<DefenceAnalysisResponse | null>(null);
  const go = useCallback((nextTab: string, nextTool?: string) => navigate({ section: "case", caseId, tab: nextTab, tool: nextTool }), [navigate, caseId]);
  const ctx: CaseToolContext = {
    caseId,
    caseTitle: legalCase?.title ?? "",
    isPolice,
    role: user.role,
    refresh,
    changed: () => setRefresh((value) => value + 1),
    datesChanged: reloadDue,
    go,
    openedAnalysis,
  };

  let body: ReactNode;
  if (!legalCase) {
    if (!active) return null;
    if (casesState === "loading") return <div className="pro-page"><RowsLoading label={`Opening this ${noun}`} rows={5} /></div>;
    if (casesState === "failed") return <div className="pro-page"><ErrorState title={`This ${noun} could not be opened.`} onRetry={reloadCases} /></div>;
    // Nothing of it is read: a case that is not in the person's own list does not exist for them.
    return (
      <div className="pro-page">
        <EmptyState icon={isPolice ? Fingerprint : BriefcaseBusiness} title={`This ${noun} cannot be opened`} action={<ProLink to={{ section: "cases" }} className="pro-button">Back to {nounPlural.toLowerCase()}</ProLink>}>
          It is not in your list. It may have been removed, or it may belong to someone else.
        </EmptyState>
      </div>
    );
  }
  const chatOpen = here && tab.key === "ask";
  if (tab.key === "overview") {
    body = <Overview legalCase={legalCase} ctx={{ ...ctx, onOpenAnalysis: (analysis) => { setOpenedAnalysis(analysis); go("strategy", "defence"); } }} />;
  } else if (tab.key === "ask") {
    body = chatOpen ? chatView({ caseId, caseTitle: legalCase.title }) : null;
  }
  const allTools = tabs.flatMap((item) => item.tools.map((entry) => ({ tab: item, tool: entry })));
  return (
    <div hidden={!active} className="pro-case" data-case-id={caseId}>
      <CaseHeader legalCase={legalCase} tabs={tabs} activeTab={tab.key} />
      <div className={`pro-case-body ${tab.tools.length > 1 ? "has-tools" : ""}`}>
        {tab.tools.length > 1 && <ToolList caseId={caseId} tab={tab} active={tool!.key} />}
        <div className="pro-case-pane">
          {body}
          {allTools.filter((entry) => visited.has(`${entry.tab.key}/${entry.tool.key}`) || `${entry.tab.key}/${entry.tool.key}` === paneKey).map((entry) => (
            <ToolPane key={`${entry.tab.key}/${entry.tool.key}`} tool={entry.tool} ctx={ctx} hidden={`${entry.tab.key}/${entry.tool.key}` !== paneKey} />
          ))}
        </div>
      </div>
    </div>
  );
}
