"use client";

import { ArrowRight, ExternalLink, Search } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError } from "@/lib/api";
import {
  CURRENCY_LABEL,
  counterpartCitation,
  lookupProvision,
  type LawLookupResult,
} from "@/lib/law-lookup";

const EXAMPLES = ["IPC 420", "BNS 103", "BNSS 173", "CrPC 154", "Article 21"];

/** Read a provision by its citation, and see what it replaced or became. */
export default function LawLookup() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<LawLookupResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const inFlight = useRef<AbortController | null>(null);
  const resultHeading = useRef<HTMLHeadingElement>(null);

  const open = useCallback(async (citation: string) => {
    const wanted = citation.trim();
    if (!wanted) return;
    inFlight.current?.abort();
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

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void open(query);
  };

  return (
    <div className="law">
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

      <div aria-live="polite">
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
                          <button type="button" onClick={() => void open(citation)}>
                            {citation}<ArrowRight size={14} aria-hidden="true" />
                          </button>
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

            {result.provisions.map((provision) => (
              <article className="law-provision" key={`${provision.title}-${provision.page_start}`}>
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
            ))}

            <p className="law-note">This shows the text held in the corpus. It is legal information, not advice.</p>
          </section>
        )}
      </div>
    </div>
  );
}
