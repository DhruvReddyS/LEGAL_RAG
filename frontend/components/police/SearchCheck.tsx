"use client";

import { Plus, Save } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";

import { errorText, ErrorNote, Field, Loading, Pill, TriToggle } from "@/components/police/shared";
import { getSearchQuestions, listSearches, saveSearch } from "@/lib/api-police";
import { FINDING_WORDS, formatMoment, fromLocalInput, toLocalInput, VERDICT_WORDS } from "@/lib/police-presentation";
import type { SearchQuestions, SearchRecordRow, TriState } from "@/lib/types-police";

type Draft = {
  place: string; basis: SearchRecordRow["basis"]; searched_at: string; grounds_recorded_at: string;
  record_sent_to_magistrate_at: string; recording_forwarded_at: string; witness_count: string;
  answers: Record<string, TriState>;
};

const blank: Draft = {
  place: "", basis: "unknown", searched_at: "", grounds_recorded_at: "", record_sent_to_magistrate_at: "",
  recording_forwarded_at: "", witness_count: "", answers: {},
};

function toDraft(row: SearchRecordRow): Draft {
  return {
    place: row.place, basis: row.basis,
    searched_at: toLocalInput(row.searched_at),
    grounds_recorded_at: toLocalInput(row.grounds_recorded_at),
    record_sent_to_magistrate_at: toLocalInput(row.record_sent_to_magistrate_at),
    recording_forwarded_at: toLocalInput(row.recording_forwarded_at),
    witness_count: row.witness_count === null ? "" : String(row.witness_count),
    answers: row.answers,
  };
}

function SearchForm({
  caseId,
  questions,
  row,
  onSaved,
}: {
  caseId: string;
  questions: SearchQuestions;
  row: SearchRecordRow | null;
  onSaved: (next: SearchRecordRow) => void;
}) {
  const [draft, setDraft] = useState<Draft>(row ? toDraft(row) : blank);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const answer = (key: string): TriState => draft.answers[key] ?? "unknown";
  const setAnswer = (key: string, value: TriState) => setDraft((c) => ({ ...c, answers: { ...c.answers, [key]: value } }));
  const shown = questions.questions.filter((q) => {
    if (q.applies_to !== "any" && draft.basis !== "unknown" && q.applies_to !== draft.basis) return false;
    if (q.only_if && answer(q.only_if) === "no") return false;
    return true;
  });
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true); setError("");
    try {
      const saved = await saveSearch(caseId, row?.id ?? null, {
        place: draft.place.trim(),
        basis: draft.basis,
        searched_at: fromLocalInput(draft.searched_at),
        grounds_recorded_at: fromLocalInput(draft.grounds_recorded_at),
        record_sent_to_magistrate_at: fromLocalInput(draft.record_sent_to_magistrate_at),
        recording_forwarded_at: fromLocalInput(draft.recording_forwarded_at),
        witness_count: draft.witness_count === "" ? null : Number(draft.witness_count),
        answers: draft.answers,
      });
      onSaved(saved);
      if (!row) setDraft(blank);
    } catch (cause) { setError(errorText(cause)); } finally { setBusy(false); }
  };
  const date = (key: keyof Draft, label: string, hint?: string) => (
    <Field label={label} hint={hint}>
      <input type="datetime-local" className="field" value={draft[key] as string} onChange={(e) => setDraft((c) => ({ ...c, [key]: e.target.value }))} />
    </Field>
  );
  return (
    <form className="police-form" onSubmit={submit} aria-label={row ? `Search at ${row.place}` : "Record a search"}>
      <div className="police-grid">
        <Field label="Place searched"><input required minLength={2} className="field" value={draft.place} onChange={(e) => setDraft((c) => ({ ...c, place: e.target.value }))} /></Field>
        <Field label="Basis">
          <select className="field" value={draft.basis} onChange={(e) => setDraft((c) => ({ ...c, basis: e.target.value as Draft["basis"] }))}>
            <option value="unknown">Not recorded</option>
            <option value="warrant">Under a search warrant</option>
            <option value="section_185">Without a warrant, under s.185</option>
          </select>
        </Field>
        {date("searched_at", "Search began")}
        {draft.basis !== "warrant" && date("grounds_recorded_at", "Grounds entered in the case diary", "s.185(1) requires this before the search. The forty-eight hours in s.185(5) are counted from it.")}
        {draft.basis !== "warrant" && date("record_sent_to_magistrate_at", "Copies sent to the Magistrate", "s.185(5)")}
        {date("recording_forwarded_at", "Recording forwarded to the Magistrate", "s.105")}
        <Field label="Independent witnesses called" hint="s.103(4) asks for two or more. Leave empty if not recorded; zero means none.">
          <input type="number" min={0} className="field" value={draft.witness_count} onChange={(e) => setDraft((c) => ({ ...c, witness_count: e.target.value }))} />
        </Field>
      </div>

      <div className="police-section-head"><h4>What applies</h4></div>
      <ul className="police-checks">
        {questions.conditions.map((condition) => (
          <li key={condition.key} className="police-check-row">
            <div className="police-check-row-top">
              <p>{condition.question}</p>
              <TriToggle label={condition.question} value={answer(condition.key)} onChange={(next) => setAnswer(condition.key, next)} />
            </div>
          </li>
        ))}
      </ul>

      <div className="police-section-head"><h4>What the record shows</h4></div>
      <ul className="police-checks">
        {shown.map((question) => (
          <li key={question.key} className="police-check-row">
            <div className="police-check-row-top">
              <p>{question.requirement}</p>
              <TriToggle label={question.requirement} value={answer(question.key)} onChange={(next) => setAnswer(question.key, next)} />
            </div>
            <small>{question.provision}</small>
          </li>
        ))}
      </ul>
      <ErrorNote message={error} />
      <div>
        <button className="button-primary" disabled={busy} type="submit">
          {row ? <Save size={15} aria-hidden="true" /> : <Plus size={15} aria-hidden="true" />}
          {row ? "Save and check again" : "Save and check"}
        </button>
      </div>
    </form>
  );
}

function SearchResult({ row, onEdit }: { row: SearchRecordRow; onEdit: () => void }) {
  const finding = FINDING_WORDS[row.finding];
  const order = { not_met: 0, cannot_be_determined: 1, met: 2, not_applicable: 3 } as const;
  const checks = [...row.checks].sort((a, b) => order[a.verdict] - order[b.verdict]);
  return (
    <article className="police-card">
      <div className="police-card-head">
        <h4>{row.place}<small>{row.basis === "warrant" ? "Under a search warrant" : row.basis === "section_185" ? "Under s.185" : "Basis not recorded"}. Search began: {formatMoment(row.searched_at)}.</small></h4>
        <Pill words={finding} />
      </div>
      <p className="police-row-detail">{finding.detail}</p>
      <ul className="police-checks">
        {checks.map((check) => (
          <li key={check.key} className="police-check-row">
            <div className="police-check-row-top">
              <p>{check.requirement}</p>
              <Pill words={VERDICT_WORDS[check.verdict]} />
            </div>
            <small><span className="provision-tag">{check.provision}</span> {check.detail}</small>
          </li>
        ))}
      </ul>
      <div><button type="button" className="police-mini" onClick={onEdit}>Update this record</button></div>
    </article>
  );
}

export function SearchCheck({ caseId }: { caseId: string }) {
  const [questions, setQuestions] = useState<SearchQuestions | null>(null);
  const [searches, setSearches] = useState<SearchRecordRow[] | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [asked, rows] = await Promise.all([getSearchQuestions(), listSearches(caseId)]);
      setQuestions(asked); setSearches(rows);
    } catch (cause) { setError(errorText(cause)); }
  }, [caseId]);
  useEffect(() => { void load(); }, [load]);

  if (error) return <ErrorNote message={error} />;
  if (!questions || !searches) return <Loading />;
  return (
    <div className="police-stack">
      <p className="police-note">
        This reads your record against BNSS ss.103, 105, 106 and 185. It does not rule on whether a search was lawful. Anything not answered stays &ldquo;cannot be determined&rdquo;, which is a record to complete rather than a defect.
      </p>
      {searches.map((row) => editing === row.id ? (
        <SearchForm
          key={row.id}
          caseId={caseId}
          questions={questions}
          row={row}
          onSaved={(next) => { setSearches((current) => (current ?? []).map((s) => (s.id === next.id ? next : s))); setEditing(null); }}
        />
      ) : (
        <SearchResult key={row.id} row={row} onEdit={() => setEditing(row.id)} />
      ))}
      <details>
        <summary className="police-link cursor-pointer">Record a search</summary>
        <div className="mt-3">
          <SearchForm caseId={caseId} questions={questions} row={null} onSaved={(next) => setSearches((current) => [...(current ?? []), next])} />
        </div>
      </details>
      {!searches.length && <p className="police-empty">No search is on record for this case.</p>}
    </div>
  );
}
