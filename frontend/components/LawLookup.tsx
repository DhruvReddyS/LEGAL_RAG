"use client";

import ActBrowser from "@/components/ActBrowser";
import { ArrowRight, Columns2, ExternalLink, Loader2, Search, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError } from "@/lib/api";
import {
  CURRENCY_LABEL,
  counterpartCitation,
  lookupProvision,
  type LawLookupResult,
  type ProvisionCounterpart,
  type ProvisionText,
} from "@/lib/law-lookup";
import { arrangeComparison } from "@/lib/law-compare";

const EXAMPLES = ["IPC 420", "BNS 103", "BNSS 173", "CrPC 154", "Article 21"];

function ProvisionArticle({ provision }: { provision: ProvisionText }) {
  return (
    <article className="law-provision">
      <header>
        <div>
          <h3>{provision.title}</h3>
          <p>{provision.jurisdiction ? `${provision.jurisdiction} · ` : ""}Page {provision.page_start === provision.page_end ? provision.page_start : `${provision.page_start}–${provision.page_end}`}</p>
        </div>
        <span className="law-status" data-status={provision.currency_status}>
          {CURRENCY_LABEL[provision.currency_status] ?? provision.currency_status}
        </span>
      </header>
      {provision.superseded_by && <p className="law-superseded">Replaced by {provision.superseded_by}.</p>}
      <pre>{provision.text}</pre>
      {provision.source_url && (
        <a href={provision.source_url} target="_blank" rel="noreferrer">
          Open the source<ExternalLink size={14} aria-hidden="true" />
        </a>
      )}
    </article>
  );
}

function CompareSide({ citation, provision, loading }: { citation: string; provision?: ProvisionText; loading?: boolean }) {
  return (
    <div className="law-compare-side">
      <h4>{citation}</h4>
      {provision
        ? <ProvisionArticle provision={provision} />
        : <p className="law-message">{loading ? "Opening…" : "The text of this provision is not held in the corpus."}</p>}
    </div>
  );
}

interface Comparison {
  item: ProvisionCounterpart;
  citation: string;
  found: LawLookupResult | null;
  failed: boolean;
}

/** Read a provision by its citation, and see what it replaced or became. */
export default function LawLookup() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<LawLookupResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const inFlight = useRef<AbortController | null>(null);
  const compareFlight = useRef<AbortController | null>(null);
  const resultHeading = useRef<HTMLHeadingElement>(null);
  const resultArea = useRef<HTMLDivElement>(null);

  const open = useCallback(async (citation: string) => {
    const wanted = citation.trim();
    if (!wanted) return;
    inFlight.current?.abort();
    compareFlight.current?.abort();
    setComparison(null);
    const controller = new AbortController();
    inFlight.current = controller;
    setQuery(wanted);
    setLoading(true);
    setError(null);
    window.history.replaceState(null, "", `?q=${encodeURIComponent(wanted)}`);
    try {
      const found = await lookupProvision(wanted, controller.signal);
      setResult(found);
      window.requestAnimationFrame(() => resultHeading.current?.focus());
    } catch (cause) {
      if (controller.signal.aborted) return;
      setResult(null);
      setError(
        cause instanceof ApiError && cause.status === 401
          ? "Sign in to look up a provision."
          : "The lookup could not be completed. Check the connection and try again.",
      );
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const initial = new URLSearchParams(window.location.search).get("q");
    if (initial) void open(initial);
    return () => inFlight.current?.abort();
  }, [open]);

  const compare = useCallback(async (item: ProvisionCounterpart, citation: string) => {
    compareFlight.current?.abort();
    const controller = new AbortController();
    compareFlight.current = controller;
    setComparison({ item, citation, found: null, failed: false });
    try {
      const found = await lookupProvision(citation, controller.signal);
      if (!controller.signal.aborted) setComparison({ item, citation, found, failed: false });
    } catch {
      if (!controller.signal.aborted) setComparison({ item, citation, found: null, failed: true });
    }
  }, []);

  const closeComparison = () => {
    compareFlight.current?.abort();
    setComparison(null);
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void open(query);
  };

  return (
    <div className="law" data-comparing={comparison ? true : undefined}>
      <header className="law-head">
        <a className="law-back" href="/">Back to Corpusil</a>
        <h1>Open a provision</h1>
        <p>Enter a citation to read the section from its source, and see what it replaced or became.</p>
      </header>

      <form className="law-search" onSubmit={submit} role="search">
        <label htmlFor="law-citation">Citation</label>
        <div className="law-search-row">
          <input
            id="law-citation"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="For example, IPC 420"
            maxLength={160}
            autoComplete="off"
            autoFocus
          />
          <button type="submit" disabled={loading || !query.trim()}>
            <Search size={16} aria-hidden="true" />
            {loading ? "Opening" : "Open"}
          </button>
        </div>
        <div className="law-examples" aria-label="Examples">
          {EXAMPLES.map((example) => (
            <button type="button" key={example} onClick={() => void open(example)}>{example}</button>
          ))}
        </div>
      </form>

      <div aria-live="polite" ref={resultArea}>
        {error && <p className="law-message law-error" role="alert">{error}</p>}

        {result && !result.understood && (
          <p className="law-message">
            That does not look like a citation. Try an Act and a section, such as “BNSS 173”. To ask a question, use <a href="/">research</a>.
          </p>
        )}

        {result?.understood && (
          <section>
            <h2 ref={resultHeading} tabIndex={-1}>{result.act}, {result.act?.startsWith("Constitution") ? "Article" : "section"} {result.section}</h2>

            {result.counterparts.length > 0 && (
              <div className="law-counterparts">
                <h3>{result.counterparts[0].from_code} and {result.counterparts[0].to_code}</h3>
                <ul>
                  {result.counterparts.map((item) => {
                    const citation = counterpartCitation(item);
                    return (
                      <li key={`${item.to_code}-${item.to_section}`}>
                        {citation ? (
                          <>
                            <button type="button" onClick={() => void open(citation)}>
                              {citation}<ArrowRight size={14} aria-hidden="true" />
                            </button>
                            <button
                              type="button"
                              className="law-compare-toggle"
                              aria-pressed={comparison?.citation === citation}
                              aria-label={`Read ${citation} side by side with this provision`}
                              onClick={() => void compare(item, citation)}
                            >
                              <Columns2 size={14} aria-hidden="true" />Side by side
                            </button>
                          </>
                        ) : (
                          <strong>Not carried forward in {item.to_code}</strong>
                        )}
                        {item.subject && <span>{item.subject}</span>}
                        {citation && item.ingredients_changed && <em>Wording or ingredients changed. Read both.</em>}
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}

            {result.provisions.length === 0 && (
              <p className="law-message">
                {result.counterparts.length > 0
                  ? "The text of this provision is not held in the corpus. Its counterpart is listed above."
                  : "This provision was not found in the corpus. Check the Act and the section number."}
              </p>
            )}

            {comparison && (() => {
              const opened = { citation: `${comparison.item.from_code} ${comparison.item.from_section}`, provision: result.provisions[0], loading: false };
              const other = { citation: comparison.citation, provision: comparison.found?.provisions[0], loading: !comparison.found && !comparison.failed };
              const { earlier, later } = arrangeComparison(comparison.item.from_code, opened, other);
              return (
                <section className="law-compare" aria-label="The two provisions side by side">
                  <div className="law-compare-head">
                    <p>
                      Both texts as held in the corpus, for reading together. It does not mark what changed.
                      {comparison.item.ingredients_changed && <strong> Wording or ingredients changed. Read both.</strong>}
                    </p>
                    <button type="button" onClick={closeComparison}><X size={14} aria-hidden="true" />Close</button>
                  </div>
                  {comparison.failed && <p className="law-message law-error" role="alert">{comparison.citation} could not be opened. Check the connection and try again.</p>}
                  {other.loading && <p className="law-message" role="status"><Loader2 size={14} className="animate-spin law-inline-icon" aria-hidden="true" />Opening {comparison.citation}</p>}
                  <div className="law-compare-sides">
                    <CompareSide {...earlier} />
                    <CompareSide {...later} />
                  </div>
                </section>
              );
            })()}

            {!comparison && result.provisions.map((provision) => (
              <ProvisionArticle key={`${provision.title}-${provision.page_start}`} provision={provision} />
            ))}

            <p className="law-note">This shows the text held in the corpus. It is legal information, not advice.</p>
          </section>
        )}
      </div>

      <ActBrowser onOpen={(citation) => { void open(citation); resultArea.current?.scrollIntoView({ block: "start" }); }} />
    </div>
  );
}
