"use client";

import { AlertTriangle, CalendarClock, CircleHelp, Clock3, Loader2, Save, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ApiError, getInvestigationFacts, getInvestigationTimeline, recordInvestigationFacts } from "@/lib/api";
import { deadlineState, summarise } from "@/lib/investigation-presentation";
import type { InvestigationDeadline, InvestigationFacts, InvestigationTimeline as Timeline, OffenceGravity } from "@/lib/types";

const EMPTY: InvestigationFacts = {
  information_recorded_at: null,
  arrested_at: null,
  first_remand_at: null,
  accused_produced_at: null,
  death_occurred_at: null,
  preliminary_enquiry_started_at: null,
  gravity: "unknown",
  is_listed_sexual_offence: false,
  is_unnatural_death: false,
};

const DATE_FIELDS: { key: keyof InvestigationFacts; label: string; hint?: string }[] = [
  { key: "information_recorded_at", label: "Information recorded", hint: "Starts the s.193(3)(ii) victim update and, for listed offences, the s.193(2) two months." },
  { key: "arrested_at", label: "Arrest", hint: "Starts the s.58 twenty-four hours." },
  { key: "first_remand_at", label: "First remand", hint: "Starts the s.187(3) period. Not the arrest — using the arrest date shortens it." },
  { key: "accused_produced_at", label: "Accused produced or appeared", hint: "Starts the s.230 fourteen days for supply of documents." },
  { key: "preliminary_enquiry_started_at", label: "Preliminary enquiry begun", hint: "s.173(3)(i) allows fourteen days." },
  { key: "death_occurred_at", label: "Death occurred", hint: "For an unnatural death: s.194 post-mortem and inquest report." },
];

/** Local datetime for an <input type="datetime-local">, which has no zone. */
function toLocalInput(value: string | null): string {
  if (!value) return "";
  const at = new Date(value);
  if (Number.isNaN(at.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())}T${pad(at.getHours())}:${pad(at.getMinutes())}`;
}

function fromLocalInput(value: string): string | null {
  if (!value) return null;
  const at = new Date(value);
  return Number.isNaN(at.getTime()) ? null : at.toISOString();
}

function formatDue(value: string): string {
  return new Date(value).toLocaleString(undefined, {
    day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

function remaining(dueAt: string): string {
  const ms = new Date(dueAt).getTime() - Date.now();
  const overdue = ms < 0;
  const hours = Math.floor(Math.abs(ms) / 3_600_000);
  const text = hours < 48 ? `${hours} hr` : `${Math.floor(hours / 24)} days`;
  return overdue ? `${text} overdue` : `${text} left`;
}

/**
 * Three states, three treatments, and the third is the point of the panel.
 *
 * A deadline that could not be computed is not compliant and is not overdue.
 * Rendering it as a quiet neutral row alongside the ones that are fine would
 * undo the whole reason the API returns null rather than false: nobody
 * established compliance here, and the reader has to see that.
 */
function DeadlineRow({ deadline }: { deadline: InvestigationDeadline }) {
  const state = deadlineState(deadline);
  const undetermined = state === "undetermined";
  const breached = state === "overdue";

  const tone = undetermined
    ? { wrap: "state-warn", accent: "text-[var(--state-warn-text)]", Icon: CircleHelp }
    : breached
      ? { wrap: "state-bad", accent: "text-[var(--state-bad-text)]", Icon: AlertTriangle }
      : { wrap: "state-ok", accent: "text-[var(--state-ok-text)]", Icon: ShieldCheck };

  return (
    <article className={`state-row ${tone.wrap}`}>
      <div className="flex items-start gap-2.5">
        <tone.Icon size={16} className={`mt-0.5 shrink-0 ${tone.accent}`} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
            <p className="state-row-title font-medium">{deadline.obligation}</p>
            <span className="provision-tag">{deadline.provision}</span>
          </div>

          {undetermined ? (
            <p className={`mt-1.5 text-xs leading-5 ${tone.accent}`}>
              <span className="font-semibold">Cannot be determined</span> — {deadline.undetermined_because}.
              This is not a finding of compliance.
            </p>
          ) : (
            <p className="state-row-detail flex flex-wrap items-center gap-x-2 gap-y-1">
              <span className={`inline-flex items-center gap-1 font-medium ${tone.accent}`}>
                <Clock3 size={12} />
                {formatDue(deadline.due_at as string)}
              </span>
              <span className={breached ? tone.accent : ""}>({remaining(deadline.due_at as string)})</span>
              {deadline.is_earliest_possible && (
                <span className="text-[10px] opacity-80">
                  earliest it can expire — s.58 excludes travel from the place of arrest
                </span>
              )}
            </p>
          )}

          <p className="state-row-detail">
            {deadline.consequence}
            {!undetermined && <> Computed as {deadline.computed_from}.</>}
          </p>
        </div>
      </div>
    </article>
  );
}

export function InvestigationTimeline({ caseId }: { caseId: string }) {
  const [facts, setFacts] = useState<InvestigationFacts>(EMPTY);
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    if (!caseId) return;
    try {
      const [stored, computed] = await Promise.all([
        getInvestigationFacts(caseId),
        getInvestigationTimeline(caseId),
      ]);
      setFacts({ ...EMPTY, ...stored });
      setTimeline(computed);
      setNotice("");
    } catch (error) {
      // 404 is the ordinary state of a matter nobody has recorded yet, and
      // must not be shown as a failure.
      if (error instanceof ApiError && error.status === 404) {
        setFacts(EMPTY);
        setTimeline(null);
        setNotice("");
        return;
      }
      setNotice(error instanceof Error ? error.message : "Could not load the timeline.");
    }
  }, [caseId]);

  useEffect(() => { void load(); }, [load]);

  const save = async () => {
    setBusy(true);
    try {
      await recordInvestigationFacts(caseId, facts);
      await load();
      setNotice("Recorded. Deadlines recomputed.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not record these dates.");
    } finally {
      setBusy(false);
    }
  };

  const counts = useMemo(() => {
    if (!timeline) return null;
    // Counted from the rows themselves rather than trusted from the two
    // summary arrays, so the badges cannot disagree with what is rendered.
    const counted = summarise(timeline.deadlines);
    return { breached: counted.overdue, undetermined: counted.undetermined, tracked: counted.tracked };
  }, [timeline]);

  if (!caseId) {
    return <p className="state-hint">Select a matter to record its investigation dates.</p>;
  }

  return (
    <div className="space-y-5">
      <div>
        <div className="flex items-center gap-2 text-sm font-semibold text-[var(--ink)]">
          <CalendarClock size={17} className="text-[var(--accent)]" />
          Statutory deadlines
        </div>
        <p className="state-hint mt-1.5">
          Computed from the BNSS by date arithmetic, not by the model. Every row names the
          provision it comes from. A date left blank produces a stated unknown rather than a guess.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        {DATE_FIELDS.map(({ key, label, hint }) => (
          <label key={key} className="block">
            <span className="block text-xs font-medium text-[var(--ink)]">{label}</span>
            <input
              type="datetime-local"
              className="field mt-1.5 h-10 w-full"
              value={toLocalInput(facts[key] as string | null)}
              onChange={(event) =>
                setFacts((current) => ({ ...current, [key]: fromLocalInput(event.target.value) }))
              }
            />
            {hint && <span className="state-field-hint">{hint}</span>}
          </label>
        ))}

        <label className="block">
          <span className="block text-xs font-medium text-[var(--ink)]">Offence gravity</span>
          <select
            className="field mt-1.5 h-10 w-full"
            value={facts.gravity}
            onChange={(event) =>
              setFacts((current) => ({ ...current, gravity: event.target.value as OffenceGravity }))
            }
          >
            <option value="unknown">Not recorded</option>
            <option value="death_life_or_ten_years_or_more">Death, life, or ten years or more</option>
            <option value="other">Any other offence</option>
          </select>
          <span className="state-field-hint">
            Left unrecorded, the s.187(3) period is reported as undetermined rather than assumed.
          </span>
        </label>

        <div className="flex flex-col justify-end gap-2">
          <label className="flex items-center gap-2 text-xs text-[var(--ink)]">
            <input
              type="checkbox"
              checked={facts.is_listed_sexual_offence}
              onChange={(event) =>
                setFacts((current) => ({ ...current, is_listed_sexual_offence: event.target.checked }))
              }
            />
            Listed offence under s.193(2) — BNS ss.64–71, POCSO ss.4, 6, 8, 10
          </label>
          <label className="flex items-center gap-2 text-xs text-[var(--ink)]">
            <input
              type="checkbox"
              checked={facts.is_unnatural_death}
              onChange={(event) =>
                setFacts((current) => ({ ...current, is_unnatural_death: event.target.checked }))
              }
            />
            Unnatural death — s.194 inquest applies
          </label>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={save}
          disabled={busy}
          className="button-primary"
        >
          {busy ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
          Record dates
        </button>
        {notice && <p className="state-hint">{notice}</p>}
      </div>

      {counts && (
        <div className="flex flex-wrap gap-2 text-[11px]">
          <span className="state-tally is-plain">{counts.tracked} obligations</span>
          {counts.breached > 0 && (
            <span className="state-tally is-bad">{counts.breached} overdue</span>
          )}
          {counts.undetermined > 0 && (
            <span className="state-tally is-warn">{counts.undetermined} cannot be determined</span>
          )}
        </div>
      )}

      <div className="space-y-2.5">
        {timeline?.deadlines.map((deadline) => (
          <DeadlineRow key={deadline.key} deadline={deadline} />
        ))}
        {timeline && timeline.deadlines.length === 0 && (
          <p className="state-row state-neutral state-hint">
            No statutory deadline follows from the dates recorded. That is not a finding that none
            applies — record the dates above and they will appear.
          </p>
        )}
        {!timeline && (
          <p className="state-row state-neutral state-hint">
            Nothing recorded for this matter yet.
          </p>
        )}
      </div>
    </div>
  );
}
