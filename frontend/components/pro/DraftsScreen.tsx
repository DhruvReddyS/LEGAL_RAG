"use client";

import { FileText, RefreshCw, Search } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { listGeneratedDocuments } from "@/lib/api";
import { listWork } from "@/lib/api-advocate";
import { listDrafts } from "@/lib/api-police";
import { workKindLabel } from "@/lib/advocate-presentation";
import { DRAFT_TITLES } from "@/lib/police-presentation";
import { plural, shortDate } from "@/lib/pro-presentation";
import type { ProRoute } from "@/lib/pro-route";
import { EmptyState, ErrorState, PageHead, ProLink, RowsLoading, usePro } from "./context";

interface DraftRow {
  id: string;
  caseId: string;
  caseTitle: string;
  title: string;
  kind: string;
  version: number;
  at: string;
  note: string;
  to: ProRoute;
}

/** There is no across-cases list on the server, so each open case is asked in turn, a few at a time. */
const AT_ONCE = 4;

async function draftsFor(caseId: string, caseTitle: string, isPolice: boolean): Promise<DraftRow[]> {
  const base = { caseId, caseTitle };
  if (isPolice) {
    const [fir, set] = await Promise.all([listGeneratedDocuments(caseId), listDrafts(caseId)]);
    return [
      ...fir.documents.map((item) => ({ ...base, id: item.id, title: "FIR draft", kind: "FIR draft", version: item.version, at: item.created_at, note: item.missing_field_count ? `${plural(item.missing_field_count, "field")} missing` : "", to: { section: "case", caseId, tab: "drafts", tool: "fir" } as ProRoute })),
      ...set.map((item) => ({ ...base, id: item.id, title: item.title || DRAFT_TITLES[item.draft_type], kind: DRAFT_TITLES[item.draft_type] ?? "Draft", version: item.version, at: item.created_at, note: item.missing_field_count ? `${plural(item.missing_field_count, "field")} missing` : "", to: { section: "case", caseId, tab: "drafts", tool: "set" } as ProRoute })),
    ];
  }
  const { work } = await listWork(caseId);
  return work.map((item) => ({
    ...base,
    id: item.id,
    title: item.title,
    kind: workKindLabel(item.kind),
    version: item.version,
    at: item.created_at,
    note: "",
    to: { section: "case", caseId, tab: item.kind === "defence_analysis" ? "strategy" : "drafts", tool: item.kind === "defence_analysis" ? "defence" : "saved" } as ProRoute,
  }));
}

export default function DraftsScreen() {
  const { cases, casesState, isPolice, noun } = usePro();
  const [rows, setRows] = useState<DraftRow[] | null>(null);
  const [unread, setUnread] = useState(0);
  const [nonce, setNonce] = useState(0);
  const [query, setQuery] = useState("");
  const [caseFilter, setCaseFilter] = useState("");
  const open = useMemo(() => cases.filter((item) => item.status === "open"), [cases]);
  const openKey = open.map((item) => item.id).join(",");
  const retry = useCallback(() => setNonce((value) => value + 1), []);
  useEffect(() => {
    if (casesState !== "ready") return;
    let cancelled = false;
    setRows(null); setUnread(0);
    void (async () => {
      const found: DraftRow[] = [];
      let failed = 0;
      const queue = [...open];
      const worker = async () => {
        for (let next = queue.shift(); next; next = queue.shift()) {
          try { found.push(...await draftsFor(next.id, next.title, isPolice)); } catch { failed += 1; }
        }
      };
      await Promise.all(Array.from({ length: AT_ONCE }, worker));
      if (!cancelled) {
        setRows(found.sort((a, b) => Date.parse(b.at) - Date.parse(a.at)));
        setUnread(failed);
      }
    })();
    return () => { cancelled = true; };
    // openKey stands in for the list: a rename must not read every case again.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [casesState, openKey, isPolice, nonce]);
  const shown = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (rows ?? []).filter((row) => (!caseFilter || row.caseId === caseFilter) && (!needle || `${row.title} ${row.kind} ${row.caseTitle}`.toLowerCase().includes(needle)));
  }, [rows, query, caseFilter]);
  const allFailed = rows !== null && !rows.length && unread > 0 && unread === open.length;
  return (
    <div className="pro-page">
      <PageHead title="Drafts" lead={`Everything drafted in your open ${noun}s, newest first. Every one is a draft for your review, not a finished document.`} />
      {casesState === "failed" || allFailed ? <ErrorState title="Your drafts could not be read." onRetry={retry} /> : null}
      {!allFailed && (casesState === "loading" || (casesState === "ready" && rows === null)) && <RowsLoading label="Reading your drafts" rows={5} />}
      {!allFailed && rows !== null && !rows.length && (
        <EmptyState icon={FileText} title="No drafts yet" action={<ProLink to={{ section: "cases" }} className="pro-button">Open a {noun}</ProLink>}>
          Open a {noun} and go to Drafts to start one. It will be listed here as well.
        </EmptyState>
      )}
      {!!rows?.length && (
        <>
          <div className="pro-toolbar">
            <label className="pro-search">
              <span className="sr-only">Search drafts</span>
              <Search size={15} aria-hidden="true" />
              <input type="search" value={query} placeholder="Search drafts" onChange={(event) => setQuery(event.target.value)} />
            </label>
            <label className="pro-select">{isPolice ? "Investigation" : "Case"}
              <select value={caseFilter} onChange={(event) => setCaseFilter(event.target.value)}>
                <option value="">All</option>
                {open.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
              </select>
            </label>
          </div>
          {unread > 0 && (
            <p className="pro-notice is-bad" role="alert">
              {plural(unread, noun)} could not be read, so this list may be short.
              <button type="button" className="pro-inline" onClick={retry}><RefreshCw size={12} aria-hidden="true" />Try again</button>
            </p>
          )}
          {shown.length ? (
            <section className="pro-card" aria-label="Drafts">
              <ul className="pro-rows">
                {shown.map((row) => (
                  <li key={`${row.caseId}-${row.id}`}>
                    <ProLink to={row.to} className="pro-activity">
                      <span className="pro-due-main">
                        <strong>{row.title}</strong>
                        <span className="pro-meta">
                          <span className="pro-meta-case">{row.caseTitle}</span>
                          <span>{row.kind}, version {row.version}</span>
                          {row.note && <span className="pro-meta-warn">{row.note}</span>}
                        </span>
                      </span>
                      <time>{shortDate(row.at)}</time>
                    </ProLink>
                  </li>
                ))}
              </ul>
            </section>
          ) : <p className="pro-quiet">No draft matches.</p>}
        </>
      )}
    </div>
  );
}
