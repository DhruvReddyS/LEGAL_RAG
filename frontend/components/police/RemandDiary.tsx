"use client";

import { Plus, Trash2 } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";

import { errorText, ErrorNote, Field, Loading } from "@/components/police/shared";
import { addDiaryEntry, addRemand, getDiary, getRemand, removeRemand } from "@/lib/api-police";
import { formatDay, formatMoment, fromLocalInput } from "@/lib/police-presentation";
import type { DiaryResponse, RemandSummary } from "@/lib/types-police";

export function RemandTracker({ caseId }: { caseId: string }) {
  const [data, setData] = useState<RemandSummary | null>(null);
  const [form, setForm] = useState({ custody_type: "police", from_date: "", to_date: "", magistrate: "", order_reference: "" });
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try { setData(await getRemand(caseId)); }
    catch (cause) { setError(errorText(cause)); }
  }, [caseId]);
  useEffect(() => { void load(); }, [load]);

  const add = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      setData(await addRemand(caseId, { ...form, magistrate: form.magistrate.trim() || null, order_reference: form.order_reference.trim() || null }));
      setForm((c) => ({ ...c, from_date: "", to_date: "", order_reference: "" }));
    } catch (cause) { setError(errorText(cause)); }
  };
  const remove = async (id: string) => {
    setError("");
    try { setData(await removeRemand(caseId, id)); }
    catch (cause) { setError(errorText(cause)); }
  };

  if (!data) return error ? <ErrorNote message={error} /> : <Loading />;
  return (
    <div className="police-stack">
      <div className="police-counts" aria-label="Custody so far">
        <div className={`police-count ${data.police_days_left === 0 ? "is-bad" : ""}`}>
          <strong>{data.police_days_used}</strong><span>Police custody days used, of fifteen</span>
        </div>
        <div className="police-count"><strong>{data.police_days_left}</strong><span>Left under {data.provision}</span></div>
        <div className="police-count"><strong>{data.judicial_days}</strong><span>Judicial custody days</span></div>
      </div>
      {data.police_custody_window_ends ? (
        <p className="police-note">
          Police custody can fall only within the initial {data.window_days} days, which end on {formatDay(data.police_custody_window_ends)} ({data.provision}), counted from the first remand on {formatDay(data.first_remand_date)}.
        </p>
      ) : (
        <p className="police-note"><strong>Cannot be determined:</strong> {data.undetermined_because}.</p>
      )}
      <p className="police-note">Both ends of a period count as whole days here, which can only warn early. How a court counts a part-day is a question for the prosecutor.</p>
      {data.findings.map((finding) => <p key={finding} className="police-error" role="alert">{finding}</p>)}
      <form className="police-form" onSubmit={add} aria-label="Add a remand period">
        <div className="police-grid">
          <Field label="Custody">
            <select className="field" value={form.custody_type} onChange={(e) => setForm((c) => ({ ...c, custody_type: e.target.value }))}>
              <option value="police">Police</option><option value="judicial">Judicial</option>
            </select>
          </Field>
          <Field label="From"><input required type="date" className="field" value={form.from_date} onChange={(e) => setForm((c) => ({ ...c, from_date: e.target.value }))} /></Field>
          <Field label="To"><input required type="date" className="field" value={form.to_date} onChange={(e) => setForm((c) => ({ ...c, to_date: e.target.value }))} /></Field>
          <Field label="Magistrate"><input className="field" value={form.magistrate} onChange={(e) => setForm((c) => ({ ...c, magistrate: e.target.value }))} /></Field>
          <Field label="Order reference"><input className="field" value={form.order_reference} onChange={(e) => setForm((c) => ({ ...c, order_reference: e.target.value }))} /></Field>
        </div>
        <ErrorNote message={error} />
        <div><button className="button-primary" type="submit"><Plus size={15} aria-hidden="true" />Add period</button></div>
      </form>
      {data.periods.length > 0 ? (
        <ul className="grid gap-2">
          {data.periods.map((period) => (
            <li key={period.id} className="police-check-row">
              <div className="police-check-row-top">
                <p>{period.custody_type === "police" ? "Police custody" : "Judicial custody"}: {formatDay(period.from_date)} to {formatDay(period.to_date)}{period.order_reference ? `. Order ${period.order_reference}` : ""}{period.magistrate ? `. ${period.magistrate}` : ""}</p>
                <button type="button" className="police-mini is-danger" aria-label={`Remove the period from ${period.from_date}`} onClick={() => void remove(period.id)}><Trash2 size={13} aria-hidden="true" />Remove</button>
              </div>
            </li>
          ))}
        </ul>
      ) : <p className="police-empty">No remand period is on record for this case.</p>}
    </div>
  );
}

const today = () => new Date().toISOString().slice(0, 10);

export function CaseDiary({ caseId }: { caseId: string }) {
  const [data, setData] = useState<DiaryResponse | null>(null);
  const blank = { entry_date: today(), information_reached_at: "", began_at: "", closed_at: "", places_visited: "", circumstances: "", statements_inserted: "", corrects_page: "" };
  const [form, setForm] = useState(blank);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try { setData(await getDiary(caseId)); }
    catch (cause) { setError(errorText(cause)); }
  }, [caseId]);
  useEffect(() => { void load(); }, [load]);

  const set = (key: keyof typeof blank) => (event: { target: { value: string } }) => setForm((c) => ({ ...c, [key]: event.target.value }));
  const add = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true); setError("");
    try {
      setData(await addDiaryEntry(caseId, {
        entry_date: form.entry_date,
        information_reached_at: fromLocalInput(form.information_reached_at),
        began_at: fromLocalInput(form.began_at),
        closed_at: fromLocalInput(form.closed_at),
        places_visited: form.places_visited.trim() || null,
        circumstances: form.circumstances.trim(),
        statements_inserted: form.statements_inserted.trim() || null,
        corrects_page: form.corrects_page ? Number(form.corrects_page) : null,
      }));
      setForm(blank);
    } catch (cause) { setError(errorText(cause)); } finally { setBusy(false); }
  };

  if (!data) return error ? <ErrorNote message={error} /> : <Loading />;
  return (
    <div className="police-stack">
      <p className="police-note">
        BNSS s.192. Entries are numbered by the server and cannot be edited, which is what makes a later insertion visible. A correction is a new entry that names the page it corrects.
      </p>
      <form className="police-form" onSubmit={add} aria-label="Add a diary entry">
        <div className="police-grid">
          <Field label="Date"><input required type="date" className="field" value={form.entry_date} onChange={set("entry_date")} /></Field>
          <Field label="Information reached the officer"><input type="datetime-local" className="field" value={form.information_reached_at} onChange={set("information_reached_at")} /></Field>
          <Field label="Investigation began"><input type="datetime-local" className="field" value={form.began_at} onChange={set("began_at")} /></Field>
          <Field label="Investigation closed"><input type="datetime-local" className="field" value={form.closed_at} onChange={set("closed_at")} /></Field>
          <Field label="Places visited"><input className="field" value={form.places_visited} onChange={set("places_visited")} /></Field>
          <Field label="Statements inserted" hint="s.192(2)"><input className="field" value={form.statements_inserted} onChange={set("statements_inserted")} /></Field>
          <Field label="Corrects page"><input type="number" min={1} className="field" value={form.corrects_page} onChange={set("corrects_page")} /></Field>
        </div>
        <Field label="Circumstances ascertained through the investigation">
          <textarea required minLength={3} className="field" value={form.circumstances} onChange={set("circumstances")} />
        </Field>
        <ErrorNote message={error} />
        <div><button className="button-primary" disabled={busy} type="submit"><Plus size={15} aria-hidden="true" />Add entry</button></div>
      </form>
      {data.days_without_entry.length > 0 && (
        <p className="police-note">
          <strong>{data.days_without_entry.length} day{data.days_without_entry.length === 1 ? "" : "s"} without an entry</strong> since the first page, most recently {formatDay(data.days_without_entry[data.days_without_entry.length - 1])}. A day with nothing to report may be just that, so this is not shown as a lapse.
        </p>
      )}
      {data.entries.length > 0 ? (
        <ol className="grid gap-2">
          {[...data.entries].reverse().map((entry) => (
            <li key={entry.id} className="police-card">
              <div className="police-card-head">
                <h4>Page {entry.page_no}: {formatDay(entry.entry_date)}{entry.corrects_page ? <small>Corrects page {entry.corrects_page}.</small> : null}</h4>
              </div>
              <p className="police-row-title">{entry.circumstances}</p>
              <dl className="police-facts">
                <div><dt>Information reached</dt><dd>{formatMoment(entry.information_reached_at)}</dd></div>
                <div><dt>Began</dt><dd>{formatMoment(entry.began_at)}</dd></div>
                <div><dt>Closed</dt><dd>{formatMoment(entry.closed_at)}</dd></div>
                <div><dt>Places</dt><dd>{entry.places_visited ?? "Not recorded"}</dd></div>
                <div><dt>Statements inserted</dt><dd>{entry.statements_inserted ?? "Not recorded"}</dd></div>
              </dl>
            </li>
          ))}
        </ol>
      ) : <p className="police-empty">The case diary has no entries yet.</p>}
    </div>
  );
}
