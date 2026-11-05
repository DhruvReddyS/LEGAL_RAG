"use client";

import { ArrowLeftRight, FileText, Loader2, PlayCircle, ThumbsDown, ThumbsUp, TimerOff } from "lucide-react";
import { useEffect, useState } from "react";
import {
  decisionRules,
  formatCount,
  formatWhen,
  gateLabel,
  gateTone,
  reasonIsSufficient,
  standingDecision,
} from "@/lib/admin-presentation";
import {
  cancelGateRun,
  getCutoverPlan,
  getReleaseState,
  queueGateRun,
  readGateDocument,
  recordReleaseDecision,
} from "@/lib/api-admin";
import type { CutoverPlan, GateEvidence, ReleaseState } from "@/lib/types-admin";
import { ConfirmDialog, Dialog, LoadState, messageOf, Notice, PanelHeading, StatusPill, Steps, useLoaded } from "./shared";

export default function ReleasePanel() {
  const { data, error, loading, reload } = useLoaded(getReleaseState, "release");
  const [label, setLabel] = useState("");

  useEffect(() => {
    if (data && !data.evidence.some(item => item.label === label)) setLabel(data.evidence[0]?.label ?? "");
  }, [data, label]);

  if (!data) return <LoadState loading={loading} error={error} onRetry={reload} />;
  const evidence = data.evidence.find(item => item.label === label) ?? null;

  return (
    <div className="admin-stack">
      <ServingCard state={data} />
      {evidence ? (
        <>
          <section className="admin-panel">
            <PanelHeading
              title="Gate results"
              description="Read from the evidence the gate suite wrote. An unfinished gate is not a pass."
              actions={
                <label className="admin-inline-field">
                  <span>Release</span>
                  <select className="field" value={label} onChange={event => setLabel(event.target.value)}>
                    {data.evidence.map(item => <option key={item.label} value={item.label}>{item.label}</option>)}
                  </select>
                </label>
              }
            />
            <GateList evidence={evidence} />
            <EvidenceDocuments evidence={evidence} />
          </section>
          <DecisionCard state={data} evidence={evidence} onDone={reload} />
        </>
      ) : (
        <Notice>No gate evidence found. Evidence appears here once a gate run has written to docs/evidence/gates.</Notice>
      )}
      <GateQueue state={data} onDone={reload} />
      <History state={data} />
    </div>
  );
}

function ServingCard({ state }: { state: ReleaseState }) {
  const [planFor, setPlanFor] = useState<string | null>(null);
  const [plan, setPlan] = useState<CutoverPlan | null>(null);
  const others = state.collections.collections.filter(item => item.name !== state.serving_collection);
  return (
    <section className="admin-panel">
      <PanelHeading title="What is serving" description="Every answer is drawn from this collection." />
      <div className="admin-serving">
        <div>
          <span>Serving now</span>
          <code>{state.serving_collection}</code>
        </div>
        {state.collections.reachable ? (
          <ul className="admin-collections">
            {state.collections.collections.map(item => {
              const standing = standingDecision(state.decisions, item.name);
              return (
                <li key={item.name}>
                  <code>{item.name}</code>
                  <span>{formatCount(item.points)} passages</span>
                  {item.name === state.serving_collection ? (
                    <StatusPill tone="ok">Serving</StatusPill>
                  ) : standing ? (
                    <StatusPill tone={standing.decision === "approve" ? "ok" : "bad"}>
                      {standing.decision === "approve" ? "Approved" : "Refused"}
                    </StatusPill>
                  ) : (
                    <StatusPill tone="neutral">No decision</StatusPill>
                  )}
                  {item.name !== state.serving_collection && standing?.decision === "approve" && (
                    <button className="button-secondary admin-compact" onClick={() => setPlanFor(item.name)}>
                      <ArrowLeftRight size={13} aria-hidden="true" /> Prepare cutover
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        ) : (
          <Notice tone="warn">The vector store could not be reached, so collection sizes are not shown.</Notice>
        )}
      </div>
      {!state.live_switch_supported && (
        <p className="admin-footnote">
          The collection is read once at startup and held for the life of the process, so it cannot be switched safely from here. A cutover is a restart, and approval gives you the exact steps.
        </p>
      )}
      <details className="admin-details">
        <summary>How to roll back</summary>
        {state.rollback ? (
          <>
            <p>Back to the last other approved collection, <code>{state.rollback.collection}</code>.</p>
            <Steps steps={state.rollback.steps} />
          </>
        ) : (
          <p>
            No other collection has been approved on record. To roll back after a cutover, set <code>QDRANT_GLOBAL_COLLECTION</code> to the previous collection and restart the backend.
            {others.length ? ` Available: ${others.map(item => item.name).join(", ")}.` : ""}
          </p>
        )}
      </details>
      {planFor && (
        <ConfirmDialog
          title="Prepare this cutover"
          confirmLabel="Show the steps"
          typed={planFor}
          body={<p>This does not change what is serving. It records that you prepared the cutover and shows the exact steps and the way back.</p>}
          onClose={() => setPlanFor(null)}
          onConfirm={async () => { setPlan(await getCutoverPlan(planFor, planFor)); }}
        />
      )}
      {plan && (
        <Dialog title={`Cut over to ${plan.collection}`} onClose={() => setPlan(null)} wide>
          <Steps steps={plan.steps} />
          <h4 className="admin-subhead">To roll back to {plan.from_collection}</h4>
          <Steps steps={plan.rollback_steps} />
        </Dialog>
      )}
    </section>
  );
}

function GateList({ evidence }: { evidence: GateEvidence }) {
  return (
    <ul className="admin-gates">
      {evidence.gates.map(gate => (
        <li key={gate.key}>
          <div className="admin-gate-head">
            <div>
              <strong>{gate.name}</strong>
              <small>{gate.checks}</small>
            </div>
            <StatusPill tone={gateTone(gate.status)}>{gateLabel(gate.status)}</StatusPill>
          </div>
          {gate.excerpt && (
            <details className="admin-details">
              <summary>Output</summary>
              <pre className="admin-pre">{gate.excerpt}</pre>
            </details>
          )}
        </li>
      ))}
    </ul>
  );
}

function EvidenceDocuments({ evidence }: { evidence: GateEvidence }) {
  const [open, setOpen] = useState<{ name: string; content: string } | null>(null);
  const [error, setError] = useState("");
  if (!evidence.documents.length) return null;
  return (
    <div className="admin-docs">
      <span>Evidence files</span>
      {evidence.documents.map(name => (
        <button
          key={name}
          className="document-chip"
          onClick={async () => {
            setError("");
            try { setOpen(await readGateDocument(evidence.label, name)); }
            catch (cause) { setError(messageOf(cause, "That file could not be opened.")); }
          }}
        >
          <FileText size={12} aria-hidden="true" /> {name}
        </button>
      ))}
      {error && <Notice tone="bad">{error}</Notice>}
      {open && (
        <Dialog title={open.name} onClose={() => setOpen(null)} wide>
          <pre className="admin-pre is-tall">{open.content}</pre>
        </Dialog>
      )}
    </div>
  );
}

function DecisionCard({ state, evidence, onDone }: { state: ReleaseState; evidence: GateEvidence; onDone: () => void }) {
  const candidates = state.collections.collections.map(item => item.name);
  const [collection, setCollection] = useState("");
  const [reason, setReason] = useState("");
  const [override, setOverride] = useState(false);
  const [busy, setBusy] = useState<"approve" | "refuse" | null>(null);
  const [notice, setNotice] = useState<{ tone: "ok" | "bad"; text: string } | null>(null);
  const target = collection || candidates.find(name => name !== state.serving_collection) || "";
  const rules = decisionRules(evidence, override);

  const decide = async (decision: "approve" | "refuse") => {
    setBusy(decision);
    setNotice(null);
    try {
      await recordReleaseDecision({
        label: evidence.label,
        collection: target,
        decision,
        reason: reason.trim(),
        override_failed_gates: decision === "approve" && override,
      });
      setNotice({ tone: "ok", text: `${decision === "approve" ? "Approval" : "Refusal"} recorded for ${target}.` });
      setReason("");
      setOverride(false);
      onDone();
    } catch (cause) {
      setNotice({ tone: "bad", text: messageOf(cause, "The decision was not recorded.") });
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="admin-panel">
      <PanelHeading title="Decide this cutover" description="A decision does not switch anything. It goes on the record with the gate results it was made on." />
      <Notice tone={evidence.all_passed ? "ok" : "warn"}>{rules.summary}</Notice>
      <div className="admin-form">
        <label className="admin-field">
          <span>Collection</span>
          {candidates.length ? (
            <select className="field" value={target} onChange={event => setCollection(event.target.value)}>
              {!target && <option value="">Nothing but the serving collection</option>}
              {candidates.map(name => <option key={name} value={name}>{name}</option>)}
            </select>
          ) : (
            <input className="field" value={collection} placeholder="global_legal_corpus_v5" onChange={event => setCollection(event.target.value)} />
          )}
        </label>
        <label className="admin-field">
          <span>Reason</span>
          <textarea className="field" rows={3} value={reason} onChange={event => setReason(event.target.value)} />
          <small>What you checked and why you decided this. At least 10 characters.</small>
        </label>
        {rules.needsOverride && (
          <label className="admin-check">
            <input type="checkbox" checked={override} onChange={event => setOverride(event.target.checked)} />
            <span>I am approving over gates that have not passed, and the reason above says why.</span>
          </label>
        )}
        <div className="admin-actions">
          <button
            className="button-primary"
            disabled={!target || !reasonIsSufficient(reason) || !rules.canApprove || busy !== null}
            onClick={() => decide("approve")}
          >
            {busy === "approve" ? <Loader2 size={14} className="animate-spin" aria-hidden="true" /> : <ThumbsUp size={14} aria-hidden="true" />} Approve
          </button>
          <button
            className="button-secondary"
            disabled={!target || !reasonIsSufficient(reason) || busy !== null}
            onClick={() => decide("refuse")}
          >
            {busy === "refuse" ? <Loader2 size={14} className="animate-spin" aria-hidden="true" /> : <ThumbsDown size={14} aria-hidden="true" />} Refuse
          </button>
        </div>
        {notice && <Notice tone={notice.tone}>{notice.text}</Notice>}
      </div>
    </section>
  );
}

function GateQueue({ state, onDone }: { state: ReleaseState; onDone: () => void }) {
  const [label, setLabel] = useState("");
  const [collection, setCollection] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState("");
  const candidates = state.collections.collections.map(item => item.name);
  const target = collection || candidates.find(name => name !== state.serving_collection) || "";
  const active = state.gate_runs.find(run => run.status === "queued" || run.status === "running");
  const blocked = state.queue_blockers.length > 0;

  return (
    <section className="admin-panel">
      <PanelHeading
        title="Run the gates"
        description="The suite takes hours, needs an idle machine and starts its own backend, so it never runs inside this one. This queues a run for the host to pick up."
      />
      {blocked ? (
        <Notice tone="warn">{state.queue_blockers.map(item => <p key={item}>{item}</p>)}</Notice>
      ) : (
        <div className="admin-form admin-form-row">
          <label className="admin-field">
            <span>Label</span>
            <input className="field" value={label} placeholder="v5-cutover-2" autoComplete="off" onChange={event => setLabel(event.target.value)} />
          </label>
          <label className="admin-field">
            <span>Collection</span>
            <select className="field" value={target} onChange={event => setCollection(event.target.value)}>
              {candidates.map(name => <option key={name} value={name}>{name}</option>)}
            </select>
          </label>
          <button className="button-primary" disabled={!label.trim() || !target} onClick={() => setConfirming(true)}>
            <PlayCircle size={14} aria-hidden="true" /> Queue a run
          </button>
        </div>
      )}
      {error && <Notice tone="bad">{error}</Notice>}
      {active && (
        <div className="admin-run">
          <div>
            <strong>{active.label}</strong>
            <small>{active.collection}, requested {formatWhen(active.requested_at)}</small>
          </div>
          <StatusPill tone="warn">{active.status === "queued" ? "Waiting for the host" : "Running"}</StatusPill>
          {active.status === "queued" && (
            <button
              className="button-secondary admin-compact"
              onClick={async () => {
                setError("");
                try { await cancelGateRun(active.id); onDone(); }
                catch (cause) { setError(messageOf(cause, "That run could not be cancelled.")); }
              }}
            >
              <TimerOff size={13} aria-hidden="true" /> Cancel
            </button>
          )}
        </div>
      )}
      {active?.status === "queued" && (
        <p className="admin-footnote">
          On the host, with the backend stopped and <code>LEGAL_RAG_BENCHMARK_PASSWORD</code> set, run <code>{state.runner_command}</code>.
        </p>
      )}
      {confirming && (
        <ConfirmDialog
          title="Queue a gate run"
          confirmLabel="Queue it"
          body={
            <ul className="admin-bullets">
              <li>It measures <code>{target}</code> and writes evidence under <code>{label.trim()}</code>.</li>
              <li>Nothing starts until someone runs it on the host. Stop the backend first: a busy machine makes the measurements worthless.</li>
              <li>Only one run can wait at a time.</li>
            </ul>
          }
          onClose={() => setConfirming(false)}
          onConfirm={async () => { await queueGateRun(label.trim(), target); setLabel(""); onDone(); }}
        />
      )}
    </section>
  );
}

function History({ state }: { state: ReleaseState }) {
  return (
    <section className="admin-panel">
      <PanelHeading title="Decisions on record" />
      {state.decisions.length ? (
        <ul className="admin-list">
          {state.decisions.map(item => (
            <li key={item.id}>
              <div className="admin-row">
                <StatusPill tone={item.decision === "approve" ? "ok" : "bad"}>{item.decision === "approve" ? "Approved" : "Refused"}</StatusPill>
                <code>{item.collection}</code>
                <span className="admin-muted">{item.label}</span>
                {item.override_failed_gates && <StatusPill tone="warn">Over failed gates</StatusPill>}
              </div>
              <p>{item.reason}</p>
              <small className="admin-muted">{item.decided_by ?? "Former administrator"}, {formatWhen(item.decided_at)}</small>
            </li>
          ))}
        </ul>
      ) : (
        <p className="admin-empty">No cutover has been decided yet.</p>
      )}
      {state.gate_runs.length > 0 && (
        <details className="admin-details">
          <summary>Gate runs</summary>
          <ul className="admin-list">
            {state.gate_runs.map(run => (
              <li key={run.id} className="admin-row">
                <strong>{run.label}</strong>
                <code>{run.collection}</code>
                <StatusPill tone={run.status === "passed" ? "ok" : run.status === "failed" ? "bad" : run.status === "cancelled" ? "neutral" : "warn"}>{run.status}</StatusPill>
                <span className="admin-muted">{formatWhen(run.requested_at)}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
