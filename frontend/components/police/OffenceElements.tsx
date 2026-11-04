"use client";

import { Save, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { errorText, ErrorNote, Field, Loading, Pill } from "@/components/police/shared";
import {
  getOffenceCatalogue,
  listAssessments,
  listEvidence,
  listWitnesses,
  removeAssessment,
  writeAssessment,
} from "@/lib/api-police";
import { ELEMENT_WORDS, OFFENCE_FINDING_WORDS } from "@/lib/police-presentation";
import type { ElementState, EvidenceItem, OffenceAssessment, OffenceCatalogueEntry, OffenceElement, Witness } from "@/lib/types-police";

type Edit = Pick<OffenceElement, "state" | "evidence_item_ids" | "witness_ids" | "note">;

function ElementRow({
  element,
  edit,
  evidence,
  witnesses,
  onChange,
}: {
  element: OffenceElement;
  edit: Edit;
  evidence: EvidenceItem[];
  witnesses: Witness[];
  onChange: (next: Edit) => void;
}) {
  const toggle = (list: "evidence_item_ids" | "witness_ids", id: string) =>
    onChange({ ...edit, [list]: edit[list].includes(id) ? edit[list].filter((x) => x !== id) : [...edit[list], id] });
  const linked = edit.evidence_item_ids.length + edit.witness_ids.length;
  return (
    <li className="police-check-row">
      <div className="police-check-row-top">
        <p>{element.element}</p>
        <Pill words={ELEMENT_WORDS[edit.state]} />
      </div>
      <div className="police-quote">
        &ldquo;{element.source_quote}&rdquo; <span className="provision-tag" style={{ fontStyle: "normal" }}>{element.provision}</span>
      </div>
      <div className="police-grid">
        <Field label="Your assessment">
          <select className="field" value={edit.state} onChange={(e) => onChange({ ...edit, state: e.target.value as ElementState })}>
            <option value="cannot_be_determined">Cannot be determined</option>
            <option value="established" disabled={linked === 0}>Established{linked === 0 ? " (link an exhibit or witness first)" : ""}</option>
            <option value="not_established">Not established</option>
          </select>
        </Field>
        <Field label="Note"><input className="field" value={edit.note} maxLength={4000} onChange={(e) => onChange({ ...edit, note: e.target.value })} /></Field>
      </div>
      {(evidence.length > 0 || witnesses.length > 0) && (
        <div className="police-chips" role="group" aria-label="What on the record supports this element">
          {evidence.map((item) => (
            <button key={item.id} type="button" className="police-chip" aria-pressed={edit.evidence_item_ids.includes(item.id)} onClick={() => toggle("evidence_item_ids", item.id)}>{item.exhibit_label}</button>
          ))}
          {witnesses.map((witness) => (
            <button key={witness.id} type="button" className="police-chip" aria-pressed={edit.witness_ids.includes(witness.id)} onClick={() => toggle("witness_ids", witness.id)}>{witness.name}</button>
          ))}
        </div>
      )}
    </li>
  );
}

function AssessmentCard({
  caseId,
  assessment,
  evidence,
  witnesses,
  onSaved,
  onRemoved,
}: {
  caseId: string;
  assessment: OffenceAssessment;
  evidence: EvidenceItem[];
  witnesses: Witness[];
  onSaved: (next: OffenceAssessment) => void;
  onRemoved: () => void;
}) {
  const initial = useMemo(
    () => Object.fromEntries(assessment.elements.map((e) => [e.key, {
      state: e.state, evidence_item_ids: e.evidence_item_ids, witness_ids: e.witness_ids, note: e.note,
    }])) as Record<string, Edit>,
    [assessment],
  );
  const [edits, setEdits] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { setEdits(initial); }, [initial]);
  const finding = OFFENCE_FINDING_WORDS[assessment.finding];
  const save = async () => {
    setBusy(true); setError("");
    try { onSaved(await writeAssessment(caseId, assessment.offence_key, edits)); }
    catch (cause) { setError(errorText(cause)); } finally { setBusy(false); }
  };
  const remove = async () => {
    setError("");
    try { await removeAssessment(caseId, assessment.offence_key); onRemoved(); }
    catch (cause) { setError(errorText(cause)); }
  };
  return (
    <article className="police-card">
      <div className="police-card-head">
        <h4>{assessment.title} <span className="provision-tag">{assessment.provision}</span></h4>
        <Pill words={finding} />
      </div>
      <p className="police-row-detail">{finding.detail}</p>
      {assessment.limits && <p className="police-row-detail">Not covered here: {assessment.limits}</p>}
      <ul className="police-checks">
        {assessment.elements.map((element) => (
          <ElementRow
            key={element.key}
            element={element}
            edit={edits[element.key]}
            evidence={evidence}
            witnesses={witnesses}
            onChange={(next) => setEdits((current) => ({ ...current, [element.key]: next }))}
          />
        ))}
      </ul>
      <ErrorNote message={error} />
      <div className="police-row-actions">
        <button type="button" className="button-primary" disabled={busy} onClick={save}><Save size={15} aria-hidden="true" />Save assessment</button>
        <button type="button" className="police-mini is-danger" onClick={remove}><Trash2 size={13} aria-hidden="true" />Remove this offence</button>
      </div>
    </article>
  );
}

export function OffenceElements({ caseId }: { caseId: string }) {
  const [catalogue, setCatalogue] = useState<OffenceCatalogueEntry[] | null>(null);
  const [assessments, setAssessments] = useState<OffenceAssessment[] | null>(null);
  const [evidence, setEvidence] = useState<EvidenceItem[]>([]);
  const [witnesses, setWitnesses] = useState<Witness[]>([]);
  const [adding, setAdding] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [offences, rows, items, people] = await Promise.all([
        getOffenceCatalogue(), listAssessments(caseId), listEvidence(caseId), listWitnesses(caseId),
      ]);
      setCatalogue(offences); setAssessments(rows);
      setEvidence(items.filter((i) => i.status !== "entered_in_error"));
      setWitnesses(people.filter((w) => w.status !== "entered_in_error"));
    } catch (cause) { setError(errorText(cause)); }
  }, [caseId]);
  useEffect(() => { void load(); }, [load]);

  const add = async () => {
    if (!adding) return;
    setError("");
    try {
      const created = await writeAssessment(caseId, adding, {});
      setAssessments((current) => [created, ...(current ?? [])]);
      setAdding("");
    } catch (cause) { setError(errorText(cause)); }
  };

  if (!catalogue || !assessments) return error ? <ErrorNote message={error} /> : <Loading />;
  const taken = new Set(assessments.map((a) => a.offence_key));
  return (
    <div className="police-stack">
      <p className="police-note">
        The elements are read from the Bharatiya Nyaya Sanhita, with the words each was taken from. Whether your evidence establishes an element is your judgment; no model reads it here. An element can be marked established only with an exhibit or witness behind it.
      </p>
      <div className="police-filters">
        <label>Add an offence
          <select className="field" value={adding} onChange={(e) => setAdding(e.target.value)}>
            <option value="">Choose…</option>
            {catalogue.filter((o) => !taken.has(o.key)).map((o) => <option key={o.key} value={o.key}>{o.title} ({o.provision})</option>)}
          </select>
        </label>
        <button type="button" className="police-mini" disabled={!adding} onClick={add}>Add</button>
      </div>
      <ErrorNote message={error} />
      {!evidence.length && !witnesses.length && (
        <p className="police-note">Add exhibits and witnesses first. They appear here to link against each element.</p>
      )}
      {assessments.map((assessment) => (
        <AssessmentCard
          key={assessment.offence_key}
          caseId={caseId}
          assessment={assessment}
          evidence={evidence}
          witnesses={witnesses}
          onSaved={(next) => setAssessments((current) => (current ?? []).map((a) => (a.offence_key === next.offence_key ? next : a)))}
          onRemoved={() => setAssessments((current) => (current ?? []).filter((a) => a.offence_key !== assessment.offence_key))}
        />
      ))}
      {!assessments.length && <p className="police-empty">No offence has been assessed in this case.</p>}
    </div>
  );
}
