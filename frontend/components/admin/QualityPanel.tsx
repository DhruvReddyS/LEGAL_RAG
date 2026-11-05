"use client";

import { FormEvent, useState } from "react";
import { countOf, formatCount, formatDay, formatDuration, formatPercent } from "@/lib/admin-presentation";
import { getQualityDashboard } from "@/lib/api-admin";
import { getReviewQueue, recordClaimVerdict, sampleForReview, type ClaimVerdict, type ReviewClaim, type ReviewItem } from "@/lib/api-corpus-lifecycle";
import { LineChart } from "./LineChart";
import { LoadState, messageOf, Notice, PanelHeading, Pager, Stat, useLoaded } from "./shared";

const WINDOWS = [7, 30, 90] as const;

const percent = (value: number | null) => (value === null ? "Not measured" : `${Math.round(value * 100)}%`);
const whole = (value: number | null) => (value === null ? "Not measured" : Math.round(value).toLocaleString("en-IN"));
const seconds = (value: number | null) => (value === null ? "Not measured" : `${value.toFixed(0)} s`);

export default function QualityPanel() {
  const [days, setDays] = useState<number>(30);
  const { data, error, loading, reload } = useLoaded(() => getQualityDashboard(days), String(days));

  if (!data) return <LoadState loading={loading} error={error} onRetry={reload} />;
  const { live, stored } = data;
  const series = live.series;
  const run = (item: { id: string; collection: string | null }) => item.collection ?? item.id;

  return (
    <div className="admin-stack">
      <section className="admin-panel">
        <PanelHeading
          title="What users received"
          description="Live numbers from answers actually given. No answer or question text is read to produce them."
          actions={
            <div className="admin-segments" role="group" aria-label="Period">
              {WINDOWS.map(value => (
                <button key={value} aria-pressed={days === value} onClick={() => setDays(value)}>{value} days</button>
              ))}
            </div>
          }
        />
        <div className="admin-stats">
          <Stat label="Answers" value={formatCount(live.totals.answers)} />
          <Stat label="Evidence refused" value={formatPercent(live.totals.abstention_rate)} hint="Answers with insufficient evidence" />
          <Stat label="Citation coverage" value={formatPercent(live.totals.citation_coverage)} hint="Answers citing at least one source" />
          <Stat label="Unsupported claims" value={formatCount(live.totals.unsupported_claims)} hint={`Caught across ${live.totals.verified_answers} verified answers`} />
          <Stat label="Latency p50" value={formatDuration(live.totals.latency_p50_ms)} hint={`p95 ${formatDuration(live.totals.latency_p95_ms)}`} />
          <Stat label="Thumbs down" value={`${formatCount(live.totals.feedback_down)} of ${formatCount(live.totals.feedback_total)}`} />
        </div>
        <div className="admin-charts">
          <LineChart title="Evidence refused" unit="Share of answers, by day" max={1} format={percent} data={series.map(day => ({ label: formatDay(day.day), value: day.abstention_rate, detail: `${day.answers} answers` }))} />
          <LineChart title="Citation coverage" unit="Share of answers, by day" max={1} format={percent} data={series.map(day => ({ label: formatDay(day.day), value: day.citation_coverage }))} />
          <LineChart title="Unsupported claims caught" unit="Count, by day" integer format={whole} data={series.map(day => ({ label: formatDay(day.day), value: day.unsupported_claims, detail: `${day.verified_answers} verified answers` }))} />
          <LineChart title="Latency p95" unit="Seconds, by day" integer format={seconds} data={series.map(day => ({ label: formatDay(day.day), value: day.latency_p95_ms === null ? null : day.latency_p95_ms / 1000 }))} />
        </div>
      </section>

      <section className="admin-panel">
        <PanelHeading
          title="Measured against the golden set"
          description="Recorded evaluation runs. These describe the system on a fixed test, not what users received, and the corpus changes between some of them: compare runs on the Models tab."
        />
        {stored.answers.length === 0 && stored.retrieval.length === 0 && (
          <Notice>No recorded evaluation runs were found in the evidence directory.</Notice>
        )}
        <div className="admin-charts">
          <LineChart title="Abstention correct" unit="Answer harness, per run" max={1} format={percent} data={stored.answers.map(item => ({ label: formatDay(item.at), value: item.abstention_correct, detail: run(item) }))} />
          <LineChart title="Citation coverage" unit="Answer harness, per run" max={1} format={percent} data={stored.answers.map(item => ({ label: formatDay(item.at), value: item.citation_coverage, detail: run(item) }))} />
          <LineChart title="Unsupported claims" unit="Answer harness, per run" integer format={whole} data={stored.answers.map(item => ({ label: formatDay(item.at), value: item.unsupported_claims_total, detail: run(item) }))} />
          <LineChart title="Latency p50" unit="Answer harness, seconds, per run" integer format={seconds} data={stored.answers.map(item => ({ label: formatDay(item.at), value: item.latency_p50_s, detail: run(item) }))} />
          <LineChart title="Recall at 5" unit="Retrieval harness, per run" max={1} format={percent} data={stored.retrieval.map(item => ({ label: formatDay(item.at), value: item.recall_at_5, detail: run(item) }))} />
          <LineChart title="Citation accuracy at 5" unit="Retrieval harness, per run" max={1} format={percent} data={stored.retrieval.map(item => ({ label: formatDay(item.at), value: item.citation_accuracy_at_5, detail: run(item) }))} />
        </div>
      </section>

      <ExpertReviewSection />
    </div>
  );
}

const REVIEW_PAGE_SIZE = 10;
const VERDICT_LABELS: Record<ClaimVerdict, string> = { correct: "Correct", incorrect: "Incorrect", unsure: "Unsure" };

function ExpertReviewSection() {
  const [status, setStatus] = useState<"open" | "done">("open");
  const [page, setPage] = useState(1);
  const [count, setCount] = useState(10);
  const [days, setDays] = useState(30);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const { data, error, loading, reload } = useLoaded(() => getReviewQueue(status, page, REVIEW_PAGE_SIZE), `${status}:${page}`);

  const sample = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      const result = await sampleForReview(count, days);
      setMessage(`Added ${result.sampled} of ${result.requested} requested answers to the queue.`);
      setStatus("open");
      setPage(1);
      reload();
    } catch (cause) { setMessage(messageOf(cause, "Could not sample answers.")); }
    finally { setBusy(false); }
  };

  const measure = data?.measure;
  return (
    <section className="admin-panel">
      <PanelHeading
        title="Expert review"
        description="A person checks sampled answers claim by claim. Case and named-matter conversations are never sampled, the question is never shown, and names and identifiers are removed by pattern. That can miss a name in free text, so report one if you see it."
      />
      {measure && (
        <div className="admin-stats">
          <Stat
            label="Claim accuracy"
            value={measure.claim_accuracy === null ? "Not measured" : formatPercent(measure.claim_accuracy)}
            hint={measure.interval_95 ? `95% interval ${formatPercent(measure.interval_95[0])} to ${formatPercent(measure.interval_95[1])}` : "No verdicts yet"}
          />
          <Stat label="Sample size" value={formatCount(measure.sample_size)} hint={`Claims decided, across ${countOf(measure.answers_reviewed, "answer")}`} />
          <Stat label="Incorrect" value={formatCount(measure.incorrect)} />
          <Stat label="Unsure" value={formatCount(measure.unsure)} hint="Reported here, not counted in the figure" />
          <Stat label="Awaiting review" value={formatCount(measure.unreviewed)} hint="Claims" />
        </div>
      )}
      <form className="admin-filters" onSubmit={sample}>
        <label className="admin-inline-field">
          <span>Answers</span>
          <input className="field" type="number" min={1} max={50} value={count} onChange={event => setCount(Number(event.target.value))} />
        </label>
        <label className="admin-inline-field">
          <span>From the last</span>
          <select className="field" value={days} onChange={event => setDays(Number(event.target.value))}>
            {WINDOWS.map(value => <option key={value} value={value}>{value} days</option>)}
          </select>
        </label>
        <button className="button-secondary admin-compact" disabled={busy}>Sample answers</button>
      </form>
      {message && <Notice>{message}</Notice>}
      <div className="admin-segments" role="group" aria-label="Review queue">
        <button aria-pressed={status === "open"} onClick={() => { setStatus("open"); setPage(1); }}>To review</button>
        <button aria-pressed={status === "done"} onClick={() => { setStatus("done"); setPage(1); }}>Reviewed</button>
      </div>
      <LoadState
        loading={loading && !data}
        error={error}
        onRetry={reload}
        empty={data && data.total === 0 ? (status === "open" ? "Nothing to review. Sample some answers." : "No answers fully reviewed yet.") : null}
      />
      {data && data.items.length > 0 && (
        <>
          <ul className="admin-list">
            {data.items.map(item => <ReviewRow key={item.id} item={item} onChanged={reload} />)}
          </ul>
          <Pager page={page} pageSize={REVIEW_PAGE_SIZE} total={data.total} onPage={setPage} noun="answers" />
        </>
      )}
    </section>
  );
}

function ReviewRow({ item, onChanged }: { item: ReviewItem; onChanged: () => void }) {
  return (
    <li>
      <small className="admin-muted">Answered {item.answered_month}</small>
      {item.claims.map(claim => <ClaimRow key={claim.id} claim={claim} onChanged={onChanged} />)}
      <h4 className="admin-subhead">Sources</h4>
      {item.citations.map((citation, index) => (
        <p key={`${citation.number}-${index}`} className="admin-note admin-wrap">
          <b>[{citation.number}] {citation.title}{citation.section ? `, s.${citation.section}` : ""}.</b> {citation.excerpt}
          {citation.source_url && <> <a className="admin-link" href={citation.source_url} target="_blank" rel="noreferrer">Official source</a></>}
        </p>
      ))}
    </li>
  );
}

function ClaimRow({ claim, onChanged }: { claim: ReviewClaim; onChanged: () => void }) {
  const [note, setNote] = useState(claim.note ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const save = async (verdict: ClaimVerdict | null) => {
    setBusy(true);
    setError("");
    try {
      await recordClaimVerdict(claim.id, verdict, note.trim() || null);
      onChanged();
    } catch (cause) { setError(messageOf(cause, "That was not saved.")); }
    finally { setBusy(false); }
  };
  return (
    <div className="admin-work">
      <p className="admin-wrap">{claim.text}</p>
      <div className="admin-segments" role="group" aria-label="Verdict">
        {(Object.keys(VERDICT_LABELS) as ClaimVerdict[]).map(name => (
          <button key={name} disabled={busy} aria-pressed={claim.verdict === name} onClick={() => save(claim.verdict === name ? null : name)}>{VERDICT_LABELS[name]}</button>
        ))}
      </div>
      <label className="admin-inline-field is-grow">
        <span>Note</span>
        <input
          className="field"
          value={note}
          maxLength={2000}
          onChange={event => setNote(event.target.value)}
          onBlur={() => { if (claim.verdict && note.trim() !== (claim.note ?? "")) void save(claim.verdict); }}
        />
      </label>
      {error && <Notice tone="bad">{error}</Notice>}
    </div>
  );
}
