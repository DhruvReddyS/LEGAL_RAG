"use client";

import { useState } from "react";
import { formatCount, formatDay, formatDuration, formatPercent } from "@/lib/admin-presentation";
import { getQualityDashboard } from "@/lib/api-admin";
import { LineChart } from "./LineChart";
import { LoadState, Notice, PanelHeading, Stat, useLoaded } from "./shared";

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
          <LineChart title="Unsupported claims caught" unit="Count, by day" format={whole} data={series.map(day => ({ label: formatDay(day.day), value: day.unsupported_claims, detail: `${day.verified_answers} verified answers` }))} />
          <LineChart title="Latency p95" unit="Seconds, by day" format={seconds} data={series.map(day => ({ label: formatDay(day.day), value: day.latency_p95_ms === null ? null : day.latency_p95_ms / 1000 }))} />
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
          <LineChart title="Unsupported claims" unit="Answer harness, per run" format={whole} data={stored.answers.map(item => ({ label: formatDay(item.at), value: item.unsupported_claims_total, detail: run(item) }))} />
          <LineChart title="Latency p50" unit="Answer harness, seconds, per run" format={seconds} data={stored.answers.map(item => ({ label: formatDay(item.at), value: item.latency_p50_s, detail: run(item) }))} />
          <LineChart title="Recall at 5" unit="Retrieval harness, per run" max={1} format={percent} data={stored.retrieval.map(item => ({ label: formatDay(item.at), value: item.recall_at_5, detail: run(item) }))} />
          <LineChart title="Citation accuracy at 5" unit="Retrieval harness, per run" max={1} format={percent} data={stored.retrieval.map(item => ({ label: formatDay(item.at), value: item.citation_accuracy_at_5, detail: run(item) }))} />
        </div>
      </section>
    </div>
  );
}
