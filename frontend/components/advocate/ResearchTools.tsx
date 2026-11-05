"use client";

import { FileSearch, GitCompareArrows, History, Loader2, ScanText } from "lucide-react";
import { useEffect, useState } from "react";

import { listIndexedCaseDocuments } from "@/lib/api";
import { checkOpponent, checkTreatment, compareJudgments, heldJudgments, searchPrecedents } from "@/lib/api-advocate";
import type { CaseDocumentSummary } from "@/lib/types";
import type { ComparisonContent, JudgmentCatalogue, OpponentResult, PrecedentResult, TreatmentResult, VerifiedClaim, WorkDetail } from "@/lib/types-advocate";
import { Badge, Bullets, CheckRows, CoverageBanner, ErrorLine, errorText, ExternalSource, Notes, SourceList } from "./shared";

function useCatalogue() {
  const [catalogue, setCatalogue] = useState<JudgmentCatalogue | null>(null);
  const [failure, setFailure] = useState("");
  useEffect(() => {
    heldJudgments().then(setCatalogue).catch((error) => setFailure(errorText(error)));
  }, []);
  return { catalogue, failure };
}

// ---------------------------------------------------------------- A-06

export function PrecedentTool() {
  const { catalogue, failure: loadFailure } = useCatalogue();
  const [query, setQuery] = useState("");
  const [holding, setHolding] = useState("");
  const [court, setCourt] = useState("");
  const [yearFrom, setYearFrom] = useState("");
  const [yearTo, setYearTo] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  const [result, setResult] = useState<PrecedentResult | null>(null);
  const courts = Object.keys(catalogue?.coverage.by_court ?? {}).sort();
  const year = (value: string) => (value.trim() ? Number.parseInt(value, 10) : undefined);
  const run = async () => {
    setBusy(true);
    setFailure("");
    try {
      setResult(await searchPrecedents({
        query: query.trim(),
        holding: holding.trim() || undefined,
        court: court || undefined,
        year_from: year(yearFrom),
        year_to: year(yearTo),
      }));
    } catch (error) {
      setFailure(errorText(error));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="adv-section">
      <CoverageBanner coverage={result?.coverage ?? catalogue?.coverage} label="What this searches" />
      <form className="adv-form" onSubmit={(event) => { event.preventDefault(); void run(); }}>
        <label className="adv-label">The issue
          <textarea className="field min-h-20 resize-y" value={query} maxLength={2000} onChange={(event) => setQuery(event.target.value)} placeholder="Default bail where the report is filed after the period has expired" />
        </label>
        <div className="adv-grid">
          <label className="adv-label">Words you expect in the holding (optional)
            <input className="field" value={holding} maxLength={1000} onChange={(event) => setHolding(event.target.value)} />
          </label>
          <label className="adv-label">Court
            <select className="field" value={court} onChange={(event) => setCourt(event.target.value)}>
              <option value="">Every court held</option>
              {courts.map((name) => <option key={name} value={name}>{name} ({catalogue?.coverage.by_court[name]})</option>)}
            </select>
          </label>
          <label className="adv-label">From year
            <input className="field" inputMode="numeric" value={yearFrom} onChange={(event) => setYearFrom(event.target.value)} placeholder={catalogue?.year_min ? String(catalogue.year_min) : ""} />
          </label>
          <label className="adv-label">To year
            <input className="field" inputMode="numeric" value={yearTo} onChange={(event) => setYearTo(event.target.value)} placeholder={catalogue?.year_max ? String(catalogue.year_max) : ""} />
          </label>
        </div>
        <div className="adv-actions">
          <button type="submit" className="button-primary" disabled={busy || query.trim().length < 3}>
            {busy ? <Loader2 size={15} className="animate-spin" /> : <FileSearch size={15} />}Search the judgments held
          </button>
        </div>
        <ErrorLine text={failure || loadFailure} />
      </form>
      {result && (
        <div className="adv-section">
          <Notes items={[result.method, ...(result.scope_note ? [result.scope_note] : [])]} />
          {result.empty_note && <p className="case-empty">{result.empty_note}</p>}
          <ul className="adv-list">
            {result.results.map((group) => (
              <li key={group.document_id} className="adv-card">
                <div className="adv-card-head">
                  <h4>{group.title}</h4>
                  <ExternalSource href={group.source_url}>Official copy</ExternalSource>
                </div>
                <p className="adv-meta">{group.court ?? "Court not recorded"}{group.decision_year ? `, ${group.decision_year}` : ", year not recorded"}</p>
                {group.passages.map(({ source, holding_language }) => (
                  <div key={source.chunk_id} className="adv-section">
                    {holding_language.length ? (
                      <div>
                        <p className="adv-subhead">Wording of a holding, as it appears</p>
                        {holding_language.map((line) => <blockquote key={line} className="adv-passage">{line}</blockquote>)}
                      </div>
                    ) : (
                      <blockquote className="adv-passage">{source.excerpt.slice(0, 420)}{source.excerpt.length > 420 ? "…" : ""}</blockquote>
                    )}
                    <SourceList sources={[source]} />
                  </div>
                ))}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- A-07

export function TreatmentTool() {
  const [reference, setReference] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  const [result, setResult] = useState<TreatmentResult | null>(null);
  const run = async () => {
    setBusy(true);
    setFailure("");
    try {
      setResult(await checkTreatment(reference.trim()));
    } catch (error) {
      setFailure(errorText(error));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="adv-section">
      <div className="adv-notice is-bad" role="note">
        <strong>Partial check of held material. This is not a citator.</strong>
        <span>It shows where the judgments held refer to a judgment or provision, and whether the statutes it rests on have been repealed. It cannot tell you whether a judgment remains an authority. Check a full citator before relying on one.</span>
      </div>
      <form className="adv-form" onSubmit={(event) => { event.preventDefault(); void run(); }}>
        <label className="adv-label">A judgment or a provision
          <input className="field" value={reference} maxLength={500} onChange={(event) => setReference(event.target.value)} placeholder="Arnesh Kumar v. State of Bihar, or section 41 of the Code of Criminal Procedure" />
        </label>
        <div className="adv-actions">
          <button type="submit" className="button-primary" disabled={busy || reference.trim().length < 3}>
            {busy ? <Loader2 size={15} className="animate-spin" /> : <History size={15} />}See what is held
          </button>
        </div>
        <ErrorLine text={failure} />
      </form>
      {result && (
        <div className="adv-section">
          <CoverageBanner coverage={result.coverage} />
          {!result.recognised && <p className="case-empty">No judgment or provision could be read from that. Try party names with &ldquo;v.&rdquo;, or &ldquo;section 41 of the Code of Criminal Procedure&rdquo;.</p>}
          <section className="adv-section">
            <h4 className="adv-heading">Is it among the judgments held?</h4>
            {result.held.length ? (
              <ul className="adv-list">
                {result.held.map((item) => (
                  <li key={item.document_id} className="adv-card">
                    <div className="adv-card-head"><h4>{item.title}</h4><Badge tone={item.confidence === "likely" ? "neutral" : "warn"}>{item.confidence === "likely" ? "Likely match" : "Possible match"}</Badge></div>
                    <p className="adv-meta">{item.court}{item.decision_year ? `, ${item.decision_year}` : ""}. {item.match_note}</p>
                    <ExternalSource href={item.source_url}>Official copy</ExternalSource>
                  </li>
                ))}
              </ul>
            ) : <p className="case-empty">Not found among the judgments held. {result.coverage.absence_note}</p>}
          </section>
          <section className="adv-section">
            <h4 className="adv-heading">Later references in the judgments held</h4>
            {result.cited_by.length ? (
              <ul className="adv-list">
                {result.cited_by.map((row) => (
                  <li key={row.document_id} className="adv-card">
                    <h4>{row.title}</h4>
                    <p className="adv-meta">{row.court}{row.decision_year ? `, ${row.decision_year}` : ""}</p>
                    {row.passages.map((passage) => (
                      <div key={passage.source.chunk_id} className="adv-section">
                        <blockquote className="adv-passage">{passage.window}</blockquote>
                        {!!passage.words_near_reference.length && (
                          <div className="adv-sources">
                            <span className="adv-meta">Words beside the reference:</span>
                            {passage.words_near_reference.map((item) => <Badge key={item.word} tone={item.cautionary ? "warn" : "neutral"}>{item.word}</Badge>)}
                          </div>
                        )}
                        <SourceList sources={[passage.source]} />
                      </div>
                    ))}
                  </li>
                ))}
              </ul>
            ) : <p className="case-empty">No reference found in the judgments held. Citations are parsed from text and can be missed, and later treatment elsewhere is invisible here.</p>}
          </section>
          {!!result.cited_by_provision.length && (
            <section className="adv-section">
              <h4 className="adv-heading">Judgments held that cite this provision</h4>
              <ul className="adv-list">
                {result.cited_by_provision.map((row) => (
                  <li key={`${row.document_id}-${row.provision}`} className="adv-date">
                    <span className="adv-grow"><strong>{row.title}</strong><span className="adv-meta" style={{ display: "block" }}>{row.court}{row.decision_year ? `, ${row.decision_year}` : ""}, pages {row.pages.join(", ")}</span></span>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {!!result.provisions.length && (
            <section className="adv-section">
              <h4 className="adv-heading">Statutory currency of what it rests on</h4>
              <CheckRows rows={result.provisions} />
            </section>
          )}
          {!!result.cites.length && (
            <details className="adv-card">
              <summary className="adv-heading">What it refers to, as parsed ({result.cites.length})</summary>
              <ul className="adv-bullets">{result.cites.map((item) => <li key={item}>{item}</li>)}</ul>
            </details>
          )}
          <Bullets title="Limits of this check" items={result.limits} />
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- A-08

export function OpponentResultView({ result }: { result: OpponentResult }) {
  return (
    <div className="adv-section">
      <CoverageBanner coverage={result.coverage} />
      <div className="adv-strength">
        <Badge tone="neutral">{result.cases.length} case(s) cited</Badge>
        <Badge tone={result.repealed_provisions ? "bad" : "neutral"}>{result.repealed_provisions} citing a repealed code</Badge>
        <Badge tone={result.needs_attention ? "warn" : "neutral"}>{result.needs_attention} {result.needs_attention === 1 ? "provision needs" : "provisions need"} attention</Badge>
      </div>
      <section className="adv-section">
        <h4 className="adv-heading">Cases</h4>
        {!result.cases.length && <p className="case-empty">No case citation was recognised. That is not a finding that the filing cites none: check it reads like &ldquo;A v. B&rdquo; or &ldquo;(2014) 8 SCC 273&rdquo;.</p>}
        <ul className="adv-list">
          {result.cases.map((row) => (
            <li key={row.reference} className="adv-card">
              <div className="adv-card-head">
                <h4>{row.reference}</h4>
                <Badge tone={row.held ? "ok" : "warn"}>{row.held ? "Held" : "Not held"}</Badge>
              </div>
              {row.proposition_context && <p className="adv-meta">Cited in the filing as: &ldquo;{row.proposition_context}&rdquo;</p>}
              {row.not_found_note && <p className="adv-meta">{row.not_found_note}</p>}
              {row.candidates.map((item) => <p key={item.document_id} className="adv-meta">{item.title}, {item.court}. {item.match_note}</p>)}
              {!!row.passages.length && <div><p className="adv-subhead">Passages nearest that use</p><SourceList sources={row.passages} /></div>}
              {row.passages.slice(0, 1).map((source) => <blockquote key={source.chunk_id} className="adv-passage">{source.excerpt.slice(0, 500)}{source.excerpt.length > 500 ? "…" : ""}</blockquote>)}
              <p className="adv-meta">Referred to in {row.cited_in_held_judgments} other held judgment(s).</p>
            </li>
          ))}
        </ul>
      </section>
      <section className="adv-section">
        <h4 className="adv-heading">Provisions</h4>
        <CheckRows rows={result.provisions} empty="No statutory citation was recognised in this text." />
      </section>
      <Bullets title="Limits of this check" items={result.limits} />
    </div>
  );
}

export function OpponentTool({ caseId }: { caseId: string }) {
  const [text, setText] = useState("");
  const [documents, setDocuments] = useState<CaseDocumentSummary[]>([]);
  const [documentId, setDocumentId] = useState("");
  const [save, setSave] = useState(true);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  const [result, setResult] = useState<OpponentResult | null>(null);
  useEffect(() => {
    listIndexedCaseDocuments(caseId).then((response) => setDocuments(response.documents)).catch(() => setDocuments([]));
  }, [caseId]);
  const run = async () => {
    setBusy(true);
    setFailure("");
    try {
      setResult(await checkOpponent(caseId, { text: text.trim() || undefined, document_id: documentId || undefined, save }));
    } catch (error) {
      setFailure(errorText(error));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="adv-section">
      <p className="adv-lede">Reads the authorities a filing cites, with no model. For each case: whether it is held, and the passage nearest the point it is cited for. For each provision: whether it has been repealed.</p>
      <form className="adv-form" onSubmit={(event) => { event.preventDefault(); void run(); }}>
        <label className="adv-label">Paste the filing
          <textarea className="field min-h-32 resize-y leading-6" value={text} maxLength={60000} onChange={(event) => setText(event.target.value)} />
        </label>
        {!!documents.length && (
          <label className="adv-label">Or read a document in this case
            <select className="field" value={documentId} onChange={(event) => setDocumentId(event.target.value)}>
              <option value="">None</option>
              {documents.map((item) => <option key={item.document_id} value={item.document_id}>{item.filename}</option>)}
            </select>
          </label>
        )}
        <div className="adv-actions">
          <button type="submit" className="button-primary" disabled={busy || (!text.trim() && !documentId)}>
            {busy ? <Loader2 size={15} className="animate-spin" /> : <ScanText size={15} />}Check the authorities
          </button>
          <label className="adv-check"><input type="checkbox" checked={save} onChange={(event) => setSave(event.target.checked)} />Keep in this case</label>
        </div>
        <ErrorLine text={failure} />
      </form>
      {result && <OpponentResultView result={result} />}
    </div>
  );
}

// ---------------------------------------------------------------- A-09

function ComparisonSide({ title, claim }: { title: string; claim: VerifiedClaim | null }) {
  return (
    <div className="adv-side">
      <p className="adv-subhead">{title}</p>
      {claim ? (<><p className="adv-meta" style={{ color: "var(--ink)" }}>{claim.text}</p><SourceList sources={claim.citations} /></>)
        : <p className="adv-meta">Nothing on this passed the check against this side&rsquo;s passages.</p>}
    </div>
  );
}

export function ComparisonView({ work }: { work: WorkDetail<ComparisonContent> }) {
  const { content } = work;
  return (
    <div className="adv-section">
      <h4 className="adv-heading">{content.first.title} / {content.second_title}</h4>
      <CoverageBanner coverage={content.coverage} />
      <Notes items={[content.note, content.limit_note]} />
      {!content.points.length && <p className="case-empty">Nothing proposed passed the check, so nothing is shown.</p>}
      <ul className="adv-list">
        {content.points.map((point) => (
          <li key={point.dimension} className="adv-card">
            <h4>{point.dimension}</h4>
            <div className="adv-compare">
              <ComparisonSide title={content.first.title} claim={point.first} />
              <ComparisonSide title={content.second_title} claim={point.second} />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function CompareTool({ caseId }: { caseId: string }) {
  const { catalogue, failure: loadFailure } = useCatalogue();
  const [first, setFirst] = useState("");
  const [mode, setMode] = useState<"judgment" | "facts">("judgment");
  const [second, setSecond] = useState("");
  const [facts, setFacts] = useState("");
  const [focus, setFocus] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  const [work, setWork] = useState<WorkDetail<ComparisonContent> | null>(null);
  const ready = !!first && (mode === "judgment" ? !!second && second !== first : facts.trim().length >= 20);
  const run = async () => {
    setBusy(true);
    setFailure("");
    try {
      setWork(await compareJudgments(caseId, {
        first_judgment_id: first,
        ...(mode === "judgment" ? { second_judgment_id: second } : { matter_facts: facts.trim() }),
        focus: focus.trim() || undefined,
      }));
    } catch (error) {
      setFailure(errorText(error));
    } finally {
      setBusy(false);
    }
  };
  const options = catalogue?.judgments ?? [];
  const label = (item: { title: string; decision_year: number | null }) => `${item.title.slice(0, 90)}${item.decision_year ? ` (${item.decision_year})` : ""}`;
  return (
    <div className="adv-section">
      <CoverageBanner coverage={catalogue?.coverage} label="You can compare only judgments this corpus holds" />
      <form className="adv-form" onSubmit={(event) => { event.preventDefault(); void run(); }}>
        <label className="adv-label">First judgment
          <select className="field" value={first} onChange={(event) => setFirst(event.target.value)}>
            <option value="">Choose</option>
            {options.map((item) => <option key={item.document_id} value={item.document_id}>{label(item)}</option>)}
          </select>
        </label>
        <fieldset className="adv-fieldset">
          <legend>Compare it with</legend>
          <div className="adv-checks">
            <label className="adv-check"><input type="radio" name="compare-mode" checked={mode === "judgment"} onChange={() => setMode("judgment")} />Another judgment</label>
            <label className="adv-check"><input type="radio" name="compare-mode" checked={mode === "facts"} onChange={() => setMode("facts")} />This matter&rsquo;s facts</label>
          </div>
          {mode === "judgment" ? (
            <select className="field" aria-label="Second judgment" value={second} onChange={(event) => setSecond(event.target.value)}>
              <option value="">Choose</option>
              {options.filter((item) => item.document_id !== first).map((item) => <option key={item.document_id} value={item.document_id}>{label(item)}</option>)}
            </select>
          ) : (
            <textarea className="field min-h-28 resize-y" aria-label="This matter's facts" value={facts} maxLength={12000} onChange={(event) => setFacts(event.target.value)} placeholder="As instructed. They are shown as your account, not as established." />
          )}
        </fieldset>
        <label className="adv-label">Focus (optional)
          <input className="field" value={focus} maxLength={1000} onChange={(event) => setFocus(event.target.value)} placeholder="The recovery and the delay in the FIR" />
        </label>
        <div className="adv-actions">
          <button type="submit" className="button-primary" disabled={busy || !ready}>
            {busy ? <Loader2 size={15} className="animate-spin" /> : <GitCompareArrows size={15} />}Compare on the facts
          </button>
          {busy && <span className="adv-meta">Reading both and checking each statement. This can take a few minutes.</span>}
        </div>
        <ErrorLine text={failure || loadFailure} />
      </form>
      {work && <ComparisonView work={work} />}
    </div>
  );
}
