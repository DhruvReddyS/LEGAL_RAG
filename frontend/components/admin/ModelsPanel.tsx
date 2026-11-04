"use client";

import { ArrowLeftRight, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { formatDay, formatDelta, formatMetric, metricLabel } from "@/lib/admin-presentation";
import { compareEvaluationRuns, getModelConfiguration, listEvaluationRuns } from "@/lib/api-admin";
import type { EvaluationRun, RunComparison } from "@/lib/types-admin";
import { LoadState, messageOf, Notice, PanelHeading, Stat, StatusPill, Steps, useLoaded } from "./shared";

function runLabel(run: EvaluationRun) {
  return `${run.kind === "answers" ? "Answers" : "Retrieval"} / ${formatDay(run.generated_at)} / ${run.collection ?? "unknown corpus"} / ${run.id}`;
}

export default function ModelsPanel() {
  const config = useLoaded(getModelConfiguration, "models");
  const runs = useLoaded(listEvaluationRuns, "runs");
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [comparison, setComparison] = useState<RunComparison | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const items = runs.data?.runs;
    if (!items?.length) return;
    // Default to the two newest of the same kind, the comparison most often wanted.
    const first = items[0];
    const second = items.find(run => run.kind === first.kind && run.id !== first.id) ?? items[1];
    setA(current => current || (second?.id ?? first.id));
    setB(current => current || first.id);
  }, [runs.data]);

  const compare = async () => {
    setBusy(true);
    setError("");
    try { setComparison(await compareEvaluationRuns(a, b)); }
    catch (cause) { setError(messageOf(cause, "Those runs could not be compared.")); }
    finally { setBusy(false); }
  };

  return (
    <div className="admin-stack">
      <section className="admin-panel">
        <PanelHeading title="Model configuration" description="What this server is running. Read at startup, so a change means a restart and a new measurement." />
        <LoadState loading={config.loading && !config.data} error={config.error} onRetry={config.reload} />
        {config.data && (
          <>
            <div className="admin-stats">
              <Stat label="Generation model" value={<code>{config.data.generation.model}</code>} />
              <Stat label="Generation slots" value={config.data.generation.concurrency} />
              <Stat label="Kept loaded for" value={config.data.generation.keep_alive} />
              <Stat label="Serving corpus" value={<code>{config.data.serving_collection}</code>} />
            </div>
            {config.data.generation.small_tier && (
              <Notice tone="bad">This model advertises a small parameter count. It performs claim verification, where a weaker judge approves claims it should refuse.</Notice>
            )}
            <details className="admin-details">
              <summary>How to change the model</summary>
              <Steps steps={config.data.change_steps} />
            </details>
          </>
        )}
      </section>

      <section className="admin-panel">
        <PanelHeading title="Prompt fingerprints" description="Derived from the code that builds each prompt, so they change exactly when a prompt does." />
        {config.data && (
          <div className="admin-table-scroll">
            <table className="admin-table">
              <thead>
                <tr><th scope="col">Prompt</th><th scope="col">Fingerprint</th><th scope="col">In the latest run</th></tr>
              </thead>
              <tbody>
                {config.data.prompts.map(prompt => (
                  <tr key={prompt.name}>
                    <td>{prompt.name.replace(/_/g, " ")}</td>
                    <td><code>{prompt.fingerprint}</code></td>
                    <td>
                      {prompt.measured_in_latest_run === null ? (
                        <StatusPill tone="neutral">No run recorded</StatusPill>
                      ) : prompt.measured_in_latest_run ? (
                        <StatusPill tone="ok">Measured</StatusPill>
                      ) : (
                        <StatusPill tone="warn">Changed since</StatusPill>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {config.data?.latest_run && <p className="admin-footnote">Latest run with prompts on record: {config.data.latest_run}</p>}
      </section>

      <section className="admin-panel">
        <PanelHeading title="Compare two evaluation runs" description="Side by side from stored evidence. It tells you when the conditions differ, because a difference then may not be an effect of the change." />
        <LoadState loading={runs.loading && !runs.data} error={runs.error} onRetry={runs.reload} empty={runs.data && runs.data.runs.length < 2 ? "At least two recorded runs are needed to compare." : null} />
        {runs.data && runs.data.runs.length >= 2 && (
          <div className="admin-form">
            <div className="admin-form-pair">
              <label className="admin-field">
                <span>Run A</span>
                <select className="field" value={a} onChange={event => setA(event.target.value)}>
                  {runs.data.runs.map(run => <option key={run.id} value={run.id}>{runLabel(run)}</option>)}
                </select>
              </label>
              <label className="admin-field">
                <span>Run B</span>
                <select className="field" value={b} onChange={event => setB(event.target.value)}>
                  {runs.data.runs.map(run => <option key={run.id} value={run.id}>{runLabel(run)}</option>)}
                </select>
              </label>
            </div>
            <div className="admin-actions">
              <button className="button-primary" disabled={!a || !b || a === b || busy} onClick={compare}>
                {busy ? <Loader2 size={14} className="animate-spin" aria-hidden="true" /> : <ArrowLeftRight size={14} aria-hidden="true" />} Compare
              </button>
              {a === b && <small className="admin-muted">Choose two different runs.</small>}
            </div>
          </div>
        )}
        {error && <Notice tone="bad">{error}</Notice>}
        {comparison && <Comparison result={comparison} />}
      </section>
    </div>
  );
}

function Comparison({ result }: { result: RunComparison }) {
  const changed = result.prompts.filter(item => item.changed);
  return (
    <div className="admin-stack is-tight">
      {result.warnings.map(warning => <Notice key={warning} tone="warn">{warning}</Notice>)}
      <div className="admin-table-scroll">
        <table className="admin-table">
          <thead>
            <tr><th scope="col">Metric</th><th scope="col">A</th><th scope="col">B</th><th scope="col">Change</th></tr>
          </thead>
          <tbody>
            {result.metrics.map(row => (
              <tr key={row.metric}>
                <td>{metricLabel(row.metric)}</td>
                <td className={row.better === "a" ? "is-better" : undefined}>{formatMetric(row.a)}</td>
                <td className={row.better === "b" ? "is-better" : undefined}>{formatMetric(row.b)}</td>
                <td>
                  {formatDelta(row.delta)}
                  {row.better && <small className="admin-muted"> {row.better === "b" ? "B better" : "A better"}</small>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h4 className="admin-subhead">Prompts</h4>
      {result.prompts.length === 0 ? (
        <p className="admin-empty">Neither run recorded its prompts.</p>
      ) : changed.length === 0 ? (
        <p className="admin-footnote">All {result.prompts.length} prompts are the same in both runs.</p>
      ) : (
        <div className="admin-table-scroll">
          <table className="admin-table">
            <thead><tr><th scope="col">Changed prompt</th><th scope="col">A</th><th scope="col">B</th></tr></thead>
            <tbody>
              {changed.map(prompt => (
                <tr key={prompt.name}>
                  <td>{prompt.name.replace(/_/g, " ")}</td>
                  <td><code>{prompt.a ?? "Not recorded"}</code></td>
                  <td><code>{prompt.b ?? "Not recorded"}</code></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
