"use client";

import { Check, RefreshCw, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { errorText, ErrorNote, Field, Loading, Pill } from "@/components/police/shared";
import { getRegister, recordCompletion, withdrawCompletion } from "@/lib/api-police";
import {
  ACTOR_WORDS,
  formatMoment,
  fromLocalInput,
  groupRegister,
  registerWords,
  timeLeft,
  toLocalInput,
} from "@/lib/police-presentation";
import type { RegisterFilters, RegisterResponse, RegisterRow, RegisterState } from "@/lib/types-police";

const STATE_FILTERS: { state: RegisterState; label: string; tone: string }[] = [
  { state: "overdue", label: "Overdue", tone: "is-bad" },
  { state: "breached", label: "Breached", tone: "is-bad" },
  { state: "due", label: "Due", tone: "" },
  { state: "unknown", label: "Cannot be determined", tone: "is-warn" },
  { state: "met", label: "Met", tone: "" },
];

function CompletionForm({ row, onDone }: { row: RegisterRow; onDone: () => void }) {
  const [when, setWhen] = useState(toLocalInput(row.completed_at ?? new Date().toISOString()));
  const [note, setNote] = useState(row.completion_note);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const save = async () => {
    const iso = fromLocalInput(when);
    if (!iso) { setError("Enter when the step was taken."); return; }
    setBusy(true); setError("");
    try { await recordCompletion(row.case_id, row.key, iso, note); onDone(); }
    catch (cause) { setError(errorText(cause)); setBusy(false); }
  };
  return (
    <div className="police-inline-form">
      <div className="police-grid">
        <Field label="When it was done">
          <input type="datetime-local" className="field" value={when} onChange={(e) => setWhen(e.target.value)} />
        </Field>
        <Field label="Note (optional)">
          <input className="field" value={note} maxLength={2000} onChange={(e) => setNote(e.target.value)} />
        </Field>
      </div>
      <ErrorNote message={error} />
      <div className="police-row-actions">
        <button type="button" className="police-mini" disabled={busy} onClick={save}><Check size={13} aria-hidden="true" />Save</button>
        <button type="button" className="police-mini" onClick={onDone}><X size={13} aria-hidden="true" />Cancel</button>
      </div>
    </div>
  );
}

function RegisterItem({
  row,
  now,
  onChanged,
  onOpenCase,
  showCase,
}: {
  row: RegisterRow;
  now: number;
  onChanged: () => void;
  onOpenCase?: (caseId: string) => void;
  showCase: boolean;
}) {
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState("");
  const words = registerWords(row);
  const left = row.due_at && !row.completed_at ? timeLeft(row.due_at, now) : "";
  const explicitlyCompleted = Boolean(row.completed_at) && !row.completion_is_derived;
  const withdraw = async () => {
    setError("");
    try { await withdrawCompletion(row.case_id, row.key); onChanged(); }
    catch (cause) { setError(errorText(cause)); }
  };
  return (
    <li className={`police-row is-${words.tone}`}>
      <div className="police-row-top">
        <span className="police-row-when">
          {row.due_at ? formatMoment(row.due_at) : "No date can be computed"}
          {left && <small className={row.state === "overdue" ? "is-over" : ""}>{left}</small>}
        </span>
        <Pill words={words} />
      </div>
      <p className="police-row-title">{row.obligation}</p>
      <div className="police-row-meta">
        <span className="provision-tag">{row.provision}</span>
        {showCase && (onOpenCase ? (
          <button type="button" className="police-link" onClick={() => onOpenCase(row.case_id)}>{row.case_title}</button>
        ) : <span>{row.case_title}</span>)}
        {!row.is_officer_duty && <span>{ACTOR_WORDS[row.actor] ?? row.actor}</span>}
      </div>
      <p className="police-row-detail">
        {row.state_reason}
        {row.is_earliest_possible && " This is the earliest the period can expire: journey time to the Magistrate is excluded."}
      </p>
      {row.completed_at && (
        <p className="police-row-detail">
          Done {formatMoment(row.completed_at)}{row.completion_is_derived ? ", from the dates recorded for this case" : ""}.
          {row.completion_note && ` ${row.completion_note}`}
        </p>
      )}
      {row.notes.map((note) => <p className="police-row-detail" key={note}>{note}</p>)}
      <ErrorNote message={error} />
      {recording ? (
        <CompletionForm row={row} onDone={() => { setRecording(false); onChanged(); }} />
      ) : (
        <div className="police-row-actions">
          <button type="button" className="police-mini" onClick={() => setRecording(true)}>
            <Check size={13} aria-hidden="true" />{row.completed_at ? "Change completion" : "Record completion"}
          </button>
          {explicitlyCompleted && (
            <button type="button" className="police-mini" onClick={withdraw}>Withdraw completion</button>
          )}
        </div>
      )}
    </li>
  );
}

const EMPTY_FILTERS: RegisterFilters = {
  states: [], caseId: "", provision: "", imminentOnly: false, officerOnly: false, includeClosed: false,
};

export function DeadlineRegister({
  cases,
  onOpenCase,
}: {
  cases: { id: string; title: string }[];
  onOpenCase?: (caseId: string) => void;
}) {
  const [filters, setFilters] = useState<RegisterFilters>(EMPTY_FILTERS);
  const [data, setData] = useState<RegisterResponse | null>(null);
  const [error, setError] = useState("");
  const [now, setNow] = useState(() => Date.now());

  const load = useCallback(async () => {
    setError("");
    try { setData(await getRegister(filters)); setNow(Date.now()); }
    catch (cause) { setData(null); setError(errorText(cause, "The register could not be read. Nothing is implied about the deadlines.")); }
  }, [filters]);
  useEffect(() => { void load(); }, [load]);

  const sections = useMemo(() => groupRegister(data?.rows ?? []), [data]);
  const toggleState = (state: RegisterState) => setFilters((current) => ({
    ...current,
    states: current.states.includes(state) ? current.states.filter((s) => s !== state) : [...current.states, state],
  }));
  const countOf = (state: RegisterState) => data?.counts[state] ?? 0;
  const urgentCount = (data?.counts.overdue ?? 0) + (data?.counts.imminent ?? 0);

  return (
    <div className="police-stack">
      <div className="police-counts" aria-label="Deadlines by state">
        <div className={`police-count ${urgentCount ? "is-bad" : "is-zero"}`}>
          <strong>{urgentCount}</strong><span>Act now: overdue or expiring within {data?.imminent_hours ?? 48} hours</span>
        </div>
        {STATE_FILTERS.map(({ state, label, tone }) => (
          <button
            type="button"
            key={state}
            className={`police-count ${countOf(state) ? tone : "is-zero"}`}
            aria-pressed={filters.states.includes(state)}
            onClick={() => toggleState(state)}
          >
            <strong>{countOf(state)}</strong><span>{label}</span>
          </button>
        ))}
      </div>

      <div className="police-filters">
        <label>Case
          <select className="field" value={filters.caseId} onChange={(e) => setFilters((c) => ({ ...c, caseId: e.target.value }))}>
            <option value="">All my cases</option>
            {cases.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
          </select>
        </label>
        <label>Provision or duty
          <input className="field" value={filters.provision} maxLength={80} placeholder="s.187, report…" onChange={(e) => setFilters((c) => ({ ...c, provision: e.target.value }))} />
        </label>
        <label className="is-check"><input type="checkbox" checked={filters.imminentOnly} onChange={(e) => setFilters((c) => ({ ...c, imminentOnly: e.target.checked }))} />Expiring soon only</label>
        <label className="is-check"><input type="checkbox" checked={filters.officerOnly} onChange={(e) => setFilters((c) => ({ ...c, officerOnly: e.target.checked }))} />My own duties only</label>
        <label className="is-check"><input type="checkbox" checked={filters.includeClosed} onChange={(e) => setFilters((c) => ({ ...c, includeClosed: e.target.checked }))} />Include closed cases</label>
        <button type="button" className="police-mini" onClick={() => void load()}><RefreshCw size={13} aria-hidden="true" />Refresh</button>
      </div>

      <ErrorNote message={error} />
      {!data && !error && <Loading label="Reading your deadlines…" />}

      {data && sections.map((section) => (
        <section key={section.key} className={`police-section ${section.key === "act_now" ? "is-urgent" : ""}`} aria-label={section.title}>
          <div className="police-section-head">
            <h4>{section.title}</h4><b>{section.rows.length}</b><small>{section.hint}</small>
          </div>
          <ul className="grid gap-2">
            {section.rows.map((row) => (
              <RegisterItem
                key={`${row.case_id}:${row.key}`}
                row={row}
                now={now}
                onChanged={() => void load()}
                onOpenCase={onOpenCase}
                showCase={!filters.caseId}
              />
            ))}
          </ul>
        </section>
      ))}

      {data && !data.rows.length && (
        <p className="police-empty">
          No deadline matches. That is not a finding that none applies: a limit appears once the date that starts it is recorded.
        </p>
      )}

      {data && data.cases_without_facts.length > 0 && (
        <section className="police-section" aria-label="Cases with nothing recorded">
          <div className="police-section-head">
            <h4>Nothing recorded</h4><b>{data.cases_without_facts.length}</b>
            <small>No limit can be computed for these. That does not mean none applies.</small>
          </div>
          <ul className="police-chips">
            {data.cases_without_facts.map((item) => (
              <li key={item.case_id}>
                {onOpenCase
                  ? <button type="button" className="police-chip" onClick={() => onOpenCase(item.case_id)}>{item.title}</button>
                  : <span className="police-chip">{item.title}</span>}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
