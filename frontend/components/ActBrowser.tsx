"use client";

import { ArrowLeft, Search } from "lucide-react";
import { useEffect, useId, useState } from "react";
import { ApiError } from "@/lib/api";
import { listActSections, searchActs, type ActSections, type ActSummary } from "@/lib/law-lookup";

const SEARCH_DELAY_MS = 250;
const BUILDING_POLL_MS = 3000;

/** Find an Act by its name, then open any of its sections in the lookup above. */
export default function ActBrowser({ onOpen }: { onOpen: (citation: string) => void }) {
  const [name, setName] = useState("");
  const [acts, setActs] = useState<ActSummary[] | null>(null);
  const [total, setTotal] = useState(0);
  const [building, setBuilding] = useState(false);
  const [error, setError] = useState("");
  const [chosen, setChosen] = useState<ActSummary | null>(null);
  const [sections, setSections] = useState<ActSections | null>(null);
  const [poll, setPoll] = useState(0);
  // Nothing is asked of the server until the reader turns to this. The page is
  // public, and a visitor reading it should not start a scroll of the corpus.
  const [engaged, setEngaged] = useState(false);
  const fieldId = useId();

  const failure = (cause: unknown) =>
    cause instanceof ApiError && cause.status === 401
      ? "Sign in to browse the Acts."
      : "The list of Acts could not be read. Check the connection and try again.";

  useEffect(() => {
    if (chosen || !engaged) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      searchActs(name.trim(), controller.signal)
        .then((found) => {
          setError("");
          setBuilding(!found.ready);
          setActs(found.acts);
          setTotal(found.total);
        })
        .catch((cause) => {
          if (controller.signal.aborted) return;
          setBuilding(false);
          setActs(null);
          setError(failure(cause));
        });
    }, SEARCH_DELAY_MS);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [name, chosen, poll, engaged]);

  // The first reader after a restart arrives before the index does.
  useEffect(() => {
    if (!building) return;
    const timer = window.setTimeout(() => setPoll((value) => value + 1), BUILDING_POLL_MS);
    return () => window.clearTimeout(timer);
  }, [building, poll]);

  useEffect(() => {
    if (!chosen) return;
    const controller = new AbortController();
    setSections(null);
    setError("");
    listActSections(chosen.id, controller.signal)
      .then(setSections)
      .catch((cause) => { if (!controller.signal.aborted) setError(failure(cause)); });
    return () => controller.abort();
  }, [chosen]);

  return (
    <section className="law-browse" aria-labelledby={`${fieldId}-heading`}>
      <h2 id={`${fieldId}-heading`}>Browse an Act</h2>
      {chosen ? (
        <>
          <button type="button" className="law-browse-back" onClick={() => { setChosen(null); setSections(null); }}>
            <ArrowLeft size={14} aria-hidden="true" />All Acts
          </button>
          <h3>{chosen.name}</h3>
          {error && <p className="law-message law-error" role="alert">{error}</p>}
          {!sections && !error && <p className="law-message" role="status">Reading the sections…</p>}
          {sections && (
            <>
              <p className="law-browse-count">{sections.sections.length} held in the corpus. Open one to read it above.</p>
              <ul className="law-browse-sections">
                {sections.sections.map((row) => (
                  <li key={row.section}>
                    <button type="button" aria-label={row.citation} onClick={() => onOpen(row.citation)}>{row.section}</button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      ) : (
        <>
          <label htmlFor={fieldId}>Name of the Act</label>
          <div className="law-browse-field">
            <Search size={15} aria-hidden="true" />
            <input
              id={fieldId}
              value={name}
              maxLength={160}
              autoComplete="off"
              placeholder="For example, consumer protection"
              onFocus={() => setEngaged(true)}
              onChange={(event) => { setEngaged(true); setName(event.target.value); }}
            />
          </div>
          <div aria-live="polite">
            {error && <p className="law-message law-error" role="alert">{error}</p>}
            {building && <p className="law-message">The list of Acts is being prepared. It will appear here shortly.</p>}
            {!building && !error && acts?.length === 0 && <p className="law-message">No Act with that name is held in the corpus.</p>}
            {!building && acts && acts.length > 0 && total > acts.length && (
              <p className="law-browse-count">Showing {acts.length} of {total}. Type more of the name to narrow this.</p>
            )}
          </div>
          {acts && acts.length > 0 && (
            <ul className="law-browse-acts">
              {acts.map((act) => (
                <li key={act.id}>
                  <button type="button" onClick={() => setChosen(act)}>
                    <span>{act.name}</span>
                    <small>{act.section_count}</small>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
