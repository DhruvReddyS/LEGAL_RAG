"use client";

import { ArrowRight, Plus } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";

import { errorText, ErrorNote, Field, Loading, Pill, TriToggle } from "@/components/police/shared";
import { addCustodyEvent, addEvidence, listEvidence, updateEvidence } from "@/lib/api-police";
import { CHAIN_WORDS, cleanForm, formatMoment, fromLocalInput } from "@/lib/police-presentation";
import type { EvidenceItem, TriState } from "@/lib/types-police";

const STATUS_LABELS: Record<string, string> = {
  held: "Held",
  sent_for_examination: "Sent for examination",
  produced_in_court: "Produced in court",
  returned: "Returned",
  entered_in_error: "Entered in error",
};

function HandOverForm({ item, onSaved }: { item: EvidenceItem; onSaved: (next: EvidenceItem) => void }) {
  const holder = item.chain?.current_holder ?? "";
  const [when, setWhen] = useState("");
  const [from, setFrom] = useState(holder);
  const [to, setTo] = useState("");
  const [purpose, setPurpose] = useState("");
  const [place, setPlace] = useState("");
  const [corrects, setCorrects] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const iso = fromLocalInput(when);
    if (!iso) { setError("Enter when the hand-over happened."); return; }
    setBusy(true); setError("");
    try {
      onSaved(await addCustodyEvent(item.case_id, item.id, {
        occurred_at: iso, from_person: from.trim(), to_person: to.trim(),
        purpose: purpose.trim() || null, place: place.trim() || null,
        corrects_event_id: corrects || null,
      }));
      setWhen(""); setTo(""); setPurpose(""); setPlace(""); setCorrects("");
    } catch (cause) { setError(errorText(cause)); } finally { setBusy(false); }
  };
  return (
    <form className="police-inline-form" onSubmit={submit}>
      <div className="police-grid">
        <Field label="When"><input required type="datetime-local" className="field" value={when} onChange={(e) => setWhen(e.target.value)} /></Field>
        <Field label="From" hint="Write the name as the last entry has it. A different spelling reads as a break, as it would to a court.">
          <input required minLength={2} className="field" value={from} onChange={(e) => setFrom(e.target.value)} />
        </Field>
        <Field label="To"><input required minLength={2} className="field" value={to} onChange={(e) => setTo(e.target.value)} /></Field>
        <Field label="Purpose"><input className="field" value={purpose} onChange={(e) => setPurpose(e.target.value)} /></Field>
        <Field label="Place"><input className="field" value={place} onChange={(e) => setPlace(e.target.value)} /></Field>
        {item.custody_events.length > 0 && (
          <Field label="Corrects an earlier entry" hint="The earlier entry stays visible, struck through. Entries are never edited.">
            <select className="field" value={corrects} onChange={(e) => setCorrects(e.target.value)}>
              <option value="">No</option>
              {item.custody_events.map((event) => (
                <option key={event.id} value={event.id}>{formatMoment(event.occurred_at)}: {event.from_person} to {event.to_person}</option>
              ))}
            </select>
          </Field>
        )}
      </div>
      <ErrorNote message={error} />
      <div><button className="police-mini" disabled={busy} type="submit"><Plus size={13} aria-hidden="true" />Add to the log</button></div>
    </form>
  );
}

function EvidenceCard({ item, onChanged }: { item: EvidenceItem; onChanged: (next: EvidenceItem) => void }) {
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  const replaced = new Set(item.custody_events.map((e) => e.corrects_event_id).filter(Boolean));
  const patch = async (changes: Record<string, unknown>) => {
    setError("");
    try { onChanged(await updateEvidence(item.case_id, item.id, changes)); }
    catch (cause) { setError(errorText(cause)); }
  };
  const words = CHAIN_WORDS[item.chain?.state ?? "cannot_be_determined"];
  return (
    <li className="police-card">
      <div className="police-card-head">
        <h4>{item.exhibit_label}: {item.description}<small>{item.category}. Last recorded holder: {item.chain?.current_holder ?? "Not recorded"}.</small></h4>
        <Pill words={words} />
      </div>
      {item.chain?.issues.map((issue) => <p key={issue} className="police-row-detail">{issue}</p>)}
      <dl className="police-facts">
        <div><dt>Seized by</dt><dd>{item.seized_by ?? "Not recorded"}</dd></div>
        <div><dt>Seized at</dt><dd>{formatMoment(item.seized_at)}</dd></div>
        <div><dt>Found at</dt><dd>{item.seized_from ?? "Not recorded"}</dd></div>
        <div><dt>Held at</dt><dd>{item.storage_location ?? "Not recorded"}</dd></div>
      </dl>
      <div className="police-grid">
        <Field label="Status">
          <select className="field" value={item.status} onChange={(e) => void patch({ status: e.target.value })}>
            {Object.entries(STATUS_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </Field>
      </div>
      {item.category === "electronic" && (
        <div className="police-check-row">
          <div className="police-check-row-top">
            <p>A certificate under BSA s.63(4) accompanies this electronic record. The sequence of custody is a head of the report under BNSS s.193(3)(i)(i).</p>
            <TriToggle label="BSA s.63(4) certificate" value={item.certificate_s63} onChange={(next: TriState) => void patch({ certificate_s63: next })} />
          </div>
          <small>Hash: {item.digital_hash ?? "Not recorded"}</small>
        </div>
      )}
      <ErrorNote message={error} />
      {item.custody_events.length > 0 ? (
        <ol className="police-chain" aria-label={`Chain of custody for ${item.exhibit_label}`}>
          {item.custody_events.map((event) => (
            <li key={event.id} className={replaced.has(event.id) ? "is-corrected" : ""}>
              <span>{event.from_person} <ArrowRight size={11} className="inline" aria-label="to" /> {event.to_person}</span>
              <small>{formatMoment(event.occurred_at)}{event.purpose ? `. ${event.purpose}` : ""}{event.place ? `. At ${event.place}` : ""}{replaced.has(event.id) ? ". Corrected by a later entry." : ""}</small>
            </li>
          ))}
        </ol>
      ) : <p className="police-row-detail">No hand-over is on record.</p>}
      {open
        ? <HandOverForm item={item} onSaved={onChanged} />
        : <div><button type="button" className="police-mini" onClick={() => setOpen(true)}><Plus size={13} aria-hidden="true" />Record a hand-over</button></div>}
    </li>
  );
}

const BLANK = { exhibit_label: "", description: "", category: "physical", seized_by: "", seized_at: "", seized_from: "", storage_location: "", digital_hash: "" };

export function EvidenceCustody({ caseId }: { caseId: string }) {
  const [items, setItems] = useState<EvidenceItem[] | null>(null);
  const [form, setForm] = useState(BLANK);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try { setItems(await listEvidence(caseId)); }
    catch (cause) { setError(errorText(cause)); }
  }, [caseId]);
  useEffect(() => { void load(); }, [load]);

  const set = (key: keyof typeof BLANK) => (event: { target: { value: string } }) => setForm((c) => ({ ...c, [key]: event.target.value }));
  const add = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true); setError("");
    try {
      const { seized_at, ...rest } = form;
      const created = await addEvidence(caseId, { ...cleanForm(rest), seized_at: fromLocalInput(seized_at) });
      setItems((current) => [...(current ?? []), created]);
      setForm(BLANK);
    } catch (cause) { setError(errorText(cause)); } finally { setBusy(false); }
  };
  const replace = (next: EvidenceItem) => setItems((current) => (current ?? []).map((item) => (item.id === next.id ? next : item)));

  return (
    <div className="police-stack">
      <p className="police-note">
        The log only grows. A hand-over cannot be edited; a mistake is corrected by a new entry that names the one it replaces, and both stay visible. Breaks are worked out from who is written down, and are for you to explain rather than a ruling on the exhibit.
      </p>
      <form className="police-form" onSubmit={add} aria-label="Add an exhibit">
        <div className="police-grid">
          <Field label="Exhibit label"><input required maxLength={60} className="field" value={form.exhibit_label} onChange={set("exhibit_label")} /></Field>
          <Field label="Description"><input required minLength={3} className="field" value={form.description} onChange={set("description")} /></Field>
          <Field label="Kind">
            <select className="field" value={form.category} onChange={set("category")}>
              <option value="physical">Physical</option><option value="document">Document</option><option value="electronic">Electronic</option><option value="biological">Biological</option><option value="other">Other</option>
            </select>
          </Field>
          <Field label="Seized by"><input className="field" value={form.seized_by} onChange={set("seized_by")} /></Field>
          <Field label="Seized at"><input type="datetime-local" className="field" value={form.seized_at} onChange={set("seized_at")} /></Field>
          <Field label="Place found"><input className="field" value={form.seized_from} onChange={set("seized_from")} /></Field>
          <Field label="Held at"><input className="field" value={form.storage_location} onChange={set("storage_location")} /></Field>
          {form.category === "electronic" && <Field label="Hash value"><input className="field" value={form.digital_hash} onChange={set("digital_hash")} /></Field>}
        </div>
        <ErrorNote message={error} />
        <div><button className="button-primary" disabled={busy} type="submit"><Plus size={15} aria-hidden="true" />Add to the inventory</button></div>
      </form>
      {items === null && !error && <Loading />}
      {items && !items.length && <p className="police-empty">Nothing is on the inventory for this case.</p>}
      {items && items.length > 0 && <ul className="grid gap-3">{items.map((item) => <EvidenceCard key={item.id} item={item} onChanged={replace} />)}</ul>}
    </div>
  );
}
