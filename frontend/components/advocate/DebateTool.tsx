"use client";

import { Loader2, MessagesSquare, Square } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { cancelDebate, listDebates, readDebate, startDebate } from "@/lib/api-advocate";
import { debateIsActive, debateStatusLine, turnsByRound } from "@/lib/advocate-presentation";
import type { DebateContent, DebateProgress, DebateRow, DebateTurn } from "@/lib/types-advocate";
import { Badge, ClaimList, ErrorLine, errorText, Notes } from "./shared";

const POLL_MS = 3000;

function Side({ title, turn }: { title: string; turn: DebateTurn | null }) {
  return (
    <div className="adv-side">
      <p className="adv-subhead">{title}</p>
      {!turn ? <p className="adv-meta">Not yet reached.</p> : (
        <>
          {turn.arguments.length ? <ClaimList claims={turn.arguments} /> : <p className="adv-meta">No argument on this side passed the check.</p>}
          <p className="adv-meta">{turn.note}</p>
        </>
      )}
    </div>
  );
}

export function DebateView({ debate }: { debate: DebateContent }) {
  return (
    <div className="adv-section">
      <h4 className="adv-heading">{debate.proposition}</h4>
      <Notes items={[debate.summary, debate.disclaimer]} />
      {!!debate.repealed_authorities.length && (
        <div className="adv-notice is-bad" role="note">
          <strong>Repealed law appears in these arguments.</strong>
          {debate.repealed_authorities.map((item) => <span key={item.title}>{item.title}{item.replaced_by ? `, replaced by ${item.replaced_by}` : ""}</span>)}
        </div>
      )}
      {turnsByRound(debate.turns).map((row) => (
        <section key={row.round} className="adv-section">
          <p className="adv-subhead">Round {row.round}</p>
          <div className="adv-round">
            <Side title="For the proposition" turn={row.for} />
            <Side title="Against the proposition" turn={row.against} />
          </div>
        </section>
      ))}
    </div>
  );
}

function newKey(): string {
  const random = typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `debate-${random}`.slice(0, 128);
}

export default function DebateTool({ caseId }: { caseId: string }) {
  const [proposition, setProposition] = useState("");
  const [facts, setFacts] = useState("");
  const [rounds, setRounds] = useState(2);
  const [debates, setDebates] = useState<DebateRow[] | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [progress, setProgress] = useState<DebateProgress | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  // A second click on a failed start must not begin a second run.
  const pendingKey = useRef<string>(newKey());

  const refreshList = useCallback(async () => {
    const response = await listDebates(caseId);
    setDebates(response.debates);
    return response.debates;
  }, [caseId]);

  useEffect(() => {
    let cancelled = false;
    refreshList()
      .then((rows) => {
        // A run in progress survives a reload: pick it back up.
        const running = rows.find((row) => debateIsActive(row.status));
        if (!cancelled && running) setActiveId(running.id);
      })
      .catch((error) => { if (!cancelled) setFailure(errorText(error)); });
    return () => { cancelled = true; };
  }, [refreshList]);

  useEffect(() => {
    if (!activeId) { setProgress(null); return; }
    let cancelled = false;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const row = await readDebate(caseId, activeId);
        if (cancelled) return;
        setProgress(row);
        setFailure("");
        if (debateIsActive(row.status)) {
          timer = window.setTimeout(() => void poll(), POLL_MS);
        } else {
          void refreshList();
        }
      } catch (error) {
        if (cancelled) return;
        // One failed poll says nothing about the job, which keeps running.
        setFailure(`${errorText(error)} Trying again.`);
        timer = window.setTimeout(() => void poll(), POLL_MS * 2);
      }
    };
    void poll();
    return () => { cancelled = true; if (timer) window.clearTimeout(timer); };
  }, [activeId, caseId, refreshList]);

  const start = async () => {
    setBusy(true);
    setFailure("");
    try {
      const job = await startDebate(caseId, { proposition: proposition.trim(), facts: facts.trim() || undefined, rounds }, pendingKey.current);
      pendingKey.current = newKey();
      setActiveId(job.id);
      await refreshList();
    } catch (error) {
      setFailure(errorText(error));
    } finally {
      setBusy(false);
    }
  };
  const cancel = async () => {
    if (!activeId) return;
    try { await cancelDebate(activeId); } catch (error) { setFailure(errorText(error)); }
  };
  const running = !!progress && debateIsActive(progress.status);
  return (
    <div className="adv-section">
      <p className="adv-lede">
        Both sides put in turn, each statement checked against the passage it cites, for you to test the argument before
        the hearing. A run takes many minutes in the background, so you can leave this page and come back. It does not say who is right.
      </p>
      <form className="adv-form" onSubmit={(event) => { event.preventDefault(); void start(); }}>
        <label className="adv-label">The proposition
          <textarea className="field min-h-20 resize-y" value={proposition} maxLength={2000} onChange={(event) => setProposition(event.target.value)} placeholder="The recovery in this case is inadmissible because the search did not follow the procedure required." />
        </label>
        <label className="adv-label">Facts as instructed (optional)
          <textarea className="field min-h-20 resize-y" value={facts} maxLength={12000} onChange={(event) => setFacts(event.target.value)} />
        </label>
        <div className="adv-actions">
          <label className="adv-label">Rounds
            <select className="field" value={rounds} onChange={(event) => setRounds(Number(event.target.value))}>
              <option value={1}>1 round: about 4 model calls</option>
              <option value={2}>2 rounds: about 8 model calls</option>
              <option value={3}>3 rounds: about 12 model calls</option>
            </select>
          </label>
          <button type="submit" className="button-primary" disabled={busy || running || proposition.trim().length < 10}>
            {busy ? <Loader2 size={15} className="animate-spin" /> : <MessagesSquare size={15} />}Start the debate
          </button>
        </div>
        <ErrorLine text={failure} />
      </form>

      {progress && (
        <section className="adv-section" aria-live="polite">
          <div className="adv-card">
            <div className="adv-card-head">
              <h4>{debateStatusLine(progress, progress.stage_label)}</h4>
              {running && (
                <button type="button" className="draft-action" onClick={() => void cancel()}>
                  <Square size={12} />Cancel
                </button>
              )}
            </div>
            <div className="adv-progress" role="progressbar" aria-valuenow={progress.progress} aria-valuemin={0} aria-valuemax={100} aria-label="Debate progress">
              <span style={{ width: `${progress.progress}%` }} />
            </div>
            <p className="adv-meta">{progress.turns_done} of {progress.turns_total} turns finished.</p>
            {progress.status === "failed" && progress.error_message && <p className="adv-error">{progress.error_message}</p>}
          </div>
          {progress.debate ? <DebateView debate={progress.debate} /> : running && <p className="adv-meta">Finished turns appear here as soon as they are checked.</p>}
        </section>
      )}

      {!!debates?.length && (
        <section className="adv-section">
          <p className="adv-subhead">Debates in this case</p>
          <ul className="adv-list">
            {debates.map((row) => (
              <li key={row.id}>
                <button type="button" className="adv-row-button" aria-current={row.id === activeId} onClick={() => setActiveId(row.id)}>
                  <span className="adv-grow">{row.proposition}</span>
                  <span className="adv-meta">{row.turns_done} of {row.turns_total} turns</span>
                  <Badge tone={row.status === "succeeded" ? "ok" : row.status === "failed" ? "bad" : "neutral"}>{row.status}</Badge>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
