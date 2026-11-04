"use client";

import { Plus } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";

import { errorText, ErrorNote, Field, Loading, Pill, TriToggle } from "@/components/police/shared";
import { addWitness, listWitnesses, updateWitness } from "@/lib/api-police";
import { formatMoment, fromLocalInput, toLocalInput, type Words } from "@/lib/police-presentation";
import type { Witness, WitnessDuty } from "@/lib/types-police";

const CATEGORIES: Record<string, string> = {
  complainant: "Complainant", victim: "Victim", eyewitness: "Eyewitness", search_witness: "Witness to a search",
  expert: "Expert", official: "Official", other: "Other",
};
const STATUSES: Record<string, string> = {
  to_be_examined: "To be examined", examined: "Examined", unavailable: "Unavailable", dropped: "Dropped", entered_in_error: "Entered in error",
};
const DUTY_WORDS: Record<WitnessDuty["state"], Words> = {
  done: { label: "Done", tone: "ok" },
  not_done: { label: "Not done", tone: "bad" },
  cannot_be_determined: { label: "Cannot be determined", tone: "warn" },
};

function WitnessCard({ witness, onChanged }: { witness: Witness; onChanged: (next: Witness) => void }) {
  const [error, setError] = useState("");
  const patch = async (changes: Record<string, unknown>) => {
    setError("");
    try { onChanged(await updateWitness(witness.case_id, witness.id, changes)); }
    catch (cause) { setError(errorText(cause)); }
  };
  return (
    <li className="police-card">
      <div className="police-card-head">
        <h4>{witness.name}<small>{CATEGORIES[witness.category] ?? witness.category}{witness.contact ? `. ${witness.contact}` : ""}</small></h4>
        <select aria-label={`Status of ${witness.name}`} className="field max-w-[190px]" style={{ minHeight: 34, padding: "4px 8px", fontSize: 12 }} value={witness.status} onChange={(e) => void patch({ status: e.target.value })}>
          {Object.entries(STATUSES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </div>
      <div className="police-grid">
        <Field label="Statement under s.180 recorded">
          <input type="datetime-local" className="field" defaultValue={toLocalInput(witness.statement_recorded_at)} onBlur={(e) => { const next = fromLocalInput(e.target.value); if (next !== witness.statement_recorded_at) void patch({ statement_recorded_at: next }); }} />
        </Field>
        <Field label="How it was recorded">
          <select className="field" value={witness.statement_mode ?? ""} onChange={(e) => void patch({ statement_mode: e.target.value || null })}>
            <option value="">Not recorded</option><option value="written">In writing</option><option value="audio_video">Audio-video</option>
          </select>
        </Field>
        <Field label="Statement before a Magistrate (s.183)">
          <input type="datetime-local" className="field" defaultValue={toLocalInput(witness.magistrate_statement_at)} onBlur={(e) => { const next = fromLocalInput(e.target.value); if (next !== witness.magistrate_statement_at) void patch({ magistrate_statement_at: next }); }} />
        </Field>
        <Field label="Bond under s.190(2)">
          <input type="datetime-local" className="field" defaultValue={toLocalInput(witness.bond_executed_at)} onBlur={(e) => { const next = fromLocalInput(e.target.value); if (next !== witness.bond_executed_at) void patch({ bond_executed_at: next }); }} />
        </Field>
      </div>
      {witness.statement_recorded_at && (
        <div className="police-check-row">
          <div className="police-check-row-top">
            <p>Inserted in the case diary (BNSS s.192(2))</p>
            <TriToggle label="Inserted in the case diary" value={witness.inserted_in_diary} onChange={(next) => void patch({ inserted_in_diary: next })} />
          </div>
          {witness.needs_woman_officer && (
            <div className="police-check-row-top">
              <p>Recorded by a woman police officer or any woman officer (BNSS s.180(3))</p>
              <TriToggle label="Recorded by a woman officer" value={witness.recorded_by_woman_officer} onChange={(next) => void patch({ recorded_by_woman_officer: next })} />
            </div>
          )}
        </div>
      )}
      {witness.duties.length > 0 && (
        <ul className="police-checks">
          {witness.duties.map((duty) => (
            <li key={duty.key} className="police-check-row">
              <div className="police-check-row-top">
                <p>{duty.duty}</p>
                {duty.key === "attendance_at_residence"
                  ? <span className="provision-tag">{duty.provision}</span>
                  : <Pill words={DUTY_WORDS[duty.state]} />}
              </div>
              {duty.key !== "attendance_at_residence" && <small>{duty.provision}</small>}
            </li>
          ))}
        </ul>
      )}
      <ErrorNote message={error} />
    </li>
  );
}

const BLANK = { name: "", category: "eyewitness", contact: "", attends_only_at_residence: false, needs_woman_officer: false };

export function WitnessTracker({ caseId }: { caseId: string }) {
  const [witnesses, setWitnesses] = useState<Witness[] | null>(null);
  const [form, setForm] = useState(BLANK);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try { setWitnesses(await listWitnesses(caseId)); }
    catch (cause) { setError(errorText(cause)); }
  }, [caseId]);
  useEffect(() => { void load(); }, [load]);

  const add = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true); setError("");
    try {
      const created = await addWitness(caseId, { ...form, contact: form.contact.trim() || null });
      setWitnesses((current) => [...(current ?? []), created]);
      setForm(BLANK);
    } catch (cause) { setError(errorText(cause)); } finally { setBusy(false); }
  };

  const open = (witnesses ?? []).filter((w) => w.status === "to_be_examined").length;
  const recorded = (witnesses ?? []).filter((w) => w.statement_recorded_at).length;
  const examinedLabel = witnesses === null ? "" : `${witnesses.length} on the tracker. ${recorded} with a statement recorded, ${open} still to be examined. Last updated ${formatMoment(new Date().toISOString())}.`;

  return (
    <div className="police-stack">
      <form className="police-form" onSubmit={add} aria-label="Add a witness">
        <div className="police-grid">
          <Field label="Name"><input required minLength={2} className="field" value={form.name} onChange={(e) => setForm((c) => ({ ...c, name: e.target.value }))} /></Field>
          <Field label="Role">
            <select className="field" value={form.category} onChange={(e) => setForm((c) => ({ ...c, category: e.target.value }))}>
              {Object.entries(CATEGORIES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </Field>
          <Field label="Contact" hint="Left out of the printed case file unless you ask for it."><input className="field" value={form.contact} onChange={(e) => setForm((c) => ({ ...c, contact: e.target.value }))} /></Field>
        </div>
        <label className="police-check">
          <input type="checkbox" checked={form.attends_only_at_residence} onChange={(e) => setForm((c) => ({ ...c, attends_only_at_residence: e.target.checked }))} />
          <span>May not be required to attend elsewhere: a male under fifteen or above sixty, a woman, a mentally or physically disabled person, or a person with acute illness (BNSS s.179(1))</span>
        </label>
        <label className="police-check">
          <input type="checkbox" checked={form.needs_woman_officer} onChange={(e) => setForm((c) => ({ ...c, needs_woman_officer: e.target.checked }))} />
          <span>A woman against whom an offence under a section listed in BNSS s.180(3) is alleged. Her statement is recorded by a woman officer.</span>
        </label>
        <ErrorNote message={error} />
        <div><button className="button-primary" disabled={busy} type="submit"><Plus size={15} aria-hidden="true" />Add to the tracker</button></div>
      </form>
      {witnesses === null && !error && <Loading />}
      {witnesses && <p className="police-note" role="status">{examinedLabel}</p>}
      {witnesses && !witnesses.length && <p className="police-empty">Nobody is on the witness tracker for this case.</p>}
      {witnesses && witnesses.length > 0 && (
        <ul className="grid gap-3">
          {witnesses.map((witness) => (
            <WitnessCard key={witness.id} witness={witness} onChanged={(next) => setWitnesses((current) => (current ?? []).map((w) => (w.id === next.id ? next : w)))} />
          ))}
        </ul>
      )}
    </div>
  );
}
