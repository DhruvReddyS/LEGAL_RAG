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
  is_custodial_death: false,
  is_rape_or_attempt: false,
  victim_examined_at: null,
  arrested_under_warrant: null,
  police_report_forwarded_at: null,
  special_statute: "none",
};

const DATE_FIELDS: { key: keyof InvestigationFacts; label: string; hint?: string }[] = [
  { key: "information_recorded_at", label: "Information recorded", hint: "Starts the s.193(3)(ii) victim update and, for listed offences, the s.193(2) two months." },
  { key: "arrested_at", label: "Arrest", hint: "Starts the twenty-four hours in s.58, or s.78 if under a warrant." },
  { key: "first_remand_at", label: "First remand", hint: "Starts the s.187(3) period. Not the arrest — using the arrest date shortens it." },
  { key: "accused_produced_at", label: "Accused produced or appeared", hint: "With a police report on record, starts the Magistrate's s.230 fourteen days for supply of documents." },
  { key: "police_report_forwarded_at", label: "Police report forwarded", hint: "s.193(3). Answers the s.187(3) and s.193(2) limits on the register, and is what s.230 needs." },
  { key: "victim_examined_at", label: "Medical examination of the woman", hint: "For rape or attempted rape. Starts the practitioner's seven days under s.184(6)." },
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
                  earliest it can expire — ss.58 and 78 exclude travel from the place of arrest
                </span>
              )}
            </p>
          )}

          <p className="state-row-detail">
            {deadline.consequence}
            {!undetermined && <> Computed as {deadline.computed_from}.</>}
          </p>
          {deadline.actor && deadline.actor !== "investigating_officer" && (
            <p className="state-row-detail font-medium">
              {deadline.actor === "magistrate" ? "This is the Magistrate's duty." : "This is the medical practitioner's duty."}
            </p>
          )}
          {deadline.notes?.map((note) => <p key={note} className="state-row-detail">{note}</p>)}
        </div>
      </div>
    </article>
  );
}

export function InvestigationTimeline({ caseId, onSaved }: { caseId: string; onSaved?: () => void }) {
  const [facts, setFacts] = useState<InvestigationFacts>(EMPTY);
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  // A failed read leaves nothing safe to save. The form would hold blanks or stale
  // values, and saving them replaces whatever is on record.
  const [loaded, setLoaded] = useState(false);

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
      setLoaded(true);
    } catch (error) {
      // 404 is the ordinary state of a matter nobody has recorded yet, and
      // must not be shown as a failure.
      if (error instanceof ApiError && error.status === 404) {
        setFacts(EMPTY);
        setTimeline(null);
        setNotice("");
        setLoaded(true);
        return;
      }
      setFacts(EMPTY);
      setTimeline(null);
      setLoaded(false);
      setNotice(error instanceof Error ? error.message : "Could not load the timeline.");
    }
  }, [caseId]);

  useEffect(() => { void load(); }, [load]);

  const save = async () => {
    setBusy(true);
    try {
      await recordInvestigationFacts(caseId, facts);
      await load();
      onSaved?.();
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
    return <p className="state-hint">Select a case to record its investigation dates.</p>;
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

        <label className="block">
          <span className="block text-xs font-medium text-[var(--ink)]">Arrest type</span>
          <select
            className="field mt-1.5 h-10 w-full"
            value={facts.arrested_under_warrant === null ? "" : String(facts.arrested_under_warrant)}
            onChange={(event) =>
              setFacts((current) => ({
                ...current,
                arrested_under_warrant: event.target.value === "" ? null : event.target.value === "true",
              }))
            }
          >
            <option value="">Not recorded</option>
            <option value="false">Without warrant (s.58)</option>
            <option value="true">Under a warrant (s.78)</option>
          </select>
        </label>

        <label className="block">
          <span className="block text-xs font-medium text-[var(--ink)]">Another statute</span>
          <select
            className="field mt-1.5 h-10 w-full"
            value={facts.special_statute}
            onChange={(event) =>
              setFacts((current) => ({ ...current, special_statute: event.target.value as InvestigationFacts["special_statute"] }))
            }
          >
            <option value="none">None recorded</option>
            <option value="ndps_s36a">NDPS Act s.36A: ss.19, 24, 27A or commercial quantity</option>
          </select>
          <span className="state-field-hint">
            NDPS s.36A(4) changes the default-bail period, so no BNSS date is computed for it.
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
            Listed under s.193(2): BNS ss.64–68, 70, 71; POCSO ss.4, 6, 8, 10. BNS s.69 is not listed
          </label>
          <label className="flex items-center gap-2 text-xs text-[var(--ink)]">
            <input
              type="checkbox"
              checked={facts.is_rape_or_attempt}
              onChange={(event) =>
                setFacts((current) => ({ ...current, is_rape_or_attempt: event.target.checked }))
              }
            />
            Rape or attempted rape of a woman: s.184. For a child victim, POCSO s.27 governs the examination
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
          <label className="flex items-center gap-2 text-xs text-[var(--ink)]">
            <input
              type="checkbox"
              checked={facts.is_custodial_death}
              onChange={(event) =>
                setFacts((current) => ({ ...current, is_custodial_death: event.target.checked }))
              }
            />
            Death in custody — s.196(6) applies
          </label>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={save}
          disabled={busy || !loaded}
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
