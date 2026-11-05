"use client";

import { FolderPlus, Plus, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { caseReference, nextDueByCase, plural, shortDate, visibleCases, type CaseSort, type CaseStatusFilter } from "@/lib/pro-presentation";
import { DuePill, EmptyState, ErrorState, PageHead, ProLink, RowsLoading, StatusPill, usePro } from "./context";

export default function CasesScreen() {
  const { cases, casesState, reloadCases, due, activity, noun, nounPlural, isPolice, casesWithoutFacts, openNewCase } = usePro();
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<CaseStatusFilter>("open");
  const [sort, setSort] = useState<CaseSort>("urgent");
  const next = useMemo(() => nextDueByCase(due), [due]);
  const rows = useMemo(() => visibleCases(cases, { query, status, sort, next, activity }), [cases, query, status, sort, next, activity]);
  const nothing = useMemo(() => new Set(casesWithoutFacts.map((item) => item.case_id)), [casesWithoutFacts]);
  const newButton = <button type="button" className="pro-button is-primary" onClick={openNewCase}><Plus size={15} aria-hidden="true" />New {noun}</button>;
  return (
    <div className="pro-page">
      <PageHead
        title={nounPlural}
        lead={isPolice ? "Each investigation keeps its own files, dates, drafts and chats." : "Each case keeps its own files, dates, drafts and chats."}
        action={newButton}
      />
      {casesState === "failed" && <ErrorState title={`Your ${nounPlural.toLowerCase()} could not be read.`} onRetry={reloadCases} />}
      {casesState === "loading" && <RowsLoading label={`Loading your ${nounPlural.toLowerCase()}`} rows={5} />}
      {casesState === "ready" && !cases.length && (
        <EmptyState icon={FolderPlus} title={`No ${noun} yet`} action={newButton}>
          Start one to keep its files, dates and drafts together. Nothing in it reaches any other {noun}.
        </EmptyState>
      )}
      {casesState === "ready" && cases.length > 0 && (
        <>
          <div className="pro-toolbar">
            <label className="pro-search">
              <span className="sr-only">Search {nounPlural.toLowerCase()} by title or reference</span>
              <Search size={15} aria-hidden="true" />
              <input type="search" value={query} placeholder="Search by title or reference" onChange={(event) => setQuery(event.target.value)} />
            </label>
            <label className="pro-select">Status
              <select value={status} onChange={(event) => setStatus(event.target.value as CaseStatusFilter)}>
                <option value="open">Open</option>
                <option value="closed">Closed</option>
                <option value="archived">Archived</option>
                <option value="all">All</option>
              </select>
            </label>
            <label className="pro-select">Sort by
              <select value={sort} onChange={(event) => setSort(event.target.value as CaseSort)}>
                <option value="urgent">Most urgent</option>
                <option value="activity">Recent activity</option>
                <option value="newest">Newest</option>
                <option value="title">Title</option>
              </select>
            </label>
          </div>
          <p className="pro-count" role="status">{plural(rows.length, status === "all" ? noun : `${status} ${noun}`)}{query.trim() ? " match your search" : ""}</p>
          {rows.length ? (
            <div className="pro-table" role="table" aria-label={nounPlural}>
              <div className="pro-table-head" role="row">
                <span role="columnheader">Title</span>
                <span role="columnheader">Status</span>
                <span role="columnheader">Next due</span>
                <span role="columnheader">Last activity</span>
              </div>
              {rows.map((item) => {
                const coming = next.get(item.id);
                const last = Math.max(activity.get(item.id) ?? 0, Date.parse(item.created_at) || 0);
                return (
                  <div role="row" key={item.id} className="pro-table-row">
                    <span role="cell" className="pro-cell-title">
                      <ProLink to={{ section: "case", caseId: item.id }}>{item.title}</ProLink>
                      <small>Ref. {caseReference(item.id)}</small>
                    </span>
                    <span role="cell"><StatusPill status={item.status} /></span>
                    <span role="cell" className="pro-cell-due">
                      {coming ? (
                        <>
                          <span className="truncate" title={coming.title}>{coming.title}</span>
                          <small>{coming.when}{coming.relative ? `, ${coming.relative}` : ""} <DuePill item={coming} /></small>
                        </>
                      ) : <small>{isPolice && nothing.has(item.id) ? "No dates recorded yet" : "Nothing due"}</small>}
                    </span>
                    <span role="cell" className="pro-cell-last"><small><span className="pro-only-phone">Last activity </span>{shortDate(last)}</small></span>
                  </div>
                );
              })}
            </div>
          ) : (
            <EmptyState icon={Search} title={`No ${noun} matches`}>
              Try another word, or set the status to All.
            </EmptyState>
          )}
        </>
      )}
    </div>
  );
}
