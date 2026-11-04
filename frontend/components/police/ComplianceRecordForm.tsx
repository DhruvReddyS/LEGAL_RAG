"use client";

import { useEffect, useState } from "react";

import { errorText, ErrorNote, Field } from "@/components/police/shared";
import { writeComplianceRecord } from "@/lib/api-police";
import { formatMoment, fromLocalInput, toLocalInput } from "@/lib/police-presentation";
import type { ComplianceRecordItem, EvidenceItem } from "@/lib/types-police";

/** The date and the evidence behind one duty. A tick alone says nothing a court can read. */
export function ComplianceRecordForm({
  caseId,
  action,
  record,
  evidence,
  onSaved,
}: {
  caseId: string;
  action: string;
  record: ComplianceRecordItem | undefined;
  evidence: EvidenceItem[];
  onSaved: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [when, setWhen] = useState("");
  const [note, setNote] = useState("");
  const [item, setItem] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setWhen(toLocalInput(record?.occurred_at));
    setNote(record?.evidence_note ?? "");
    setItem(record?.evidence_item_id ?? "");
  }, [record?.occurred_at, record?.evidence_note, record?.evidence_item_id]);

  if (!record) return null;
  const has = record.occurred_at || record.evidence_note || record.evidence_item_id;
  const save = async () => {
    setBusy(true); setError("");
    try {
      await writeComplianceRecord(caseId, action, record.key, {
        occurred_at: fromLocalInput(when),
        evidence_note: note.trim() || null,
        evidence_item_id: item || null,
      });
      setOpen(false);
      onSaved();
    } catch (cause) { setError(errorText(cause)); } finally { setBusy(false); }
  };
  return (
    <>
      {has ? (
        <p className="police-record-line">
          {record.occurred_at && <>On {formatMoment(record.occurred_at)}. </>}
          {record.evidence_label && <>Exhibit {record.evidence_label}. </>}
          {record.evidence_note}
        </p>
      ) : record.needs_record ? (
        <p className="police-record-line is-missing">Marked done, with no date or evidence recorded.</p>
      ) : null}
      <details className="police-compliance-record" open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
        <summary>{has ? "Change the date or evidence" : "Add the date and evidence"}</summary>
        <div className="police-inline-form mt-2">
          <div className="police-grid">
            <Field label="When"><input type="datetime-local" className="field" value={when} onChange={(e) => setWhen(e.target.value)} /></Field>
            <Field label="Exhibit">
              <select className="field" value={item} onChange={(e) => setItem(e.target.value)}>
                <option value="">None</option>
                {evidence.map((entry) => <option key={entry.id} value={entry.id}>{entry.exhibit_label}: {entry.description}</option>)}
              </select>
            </Field>
            <Field label="What shows it" hint="For example: memo no., page of the station book.">
              <input className="field" value={note} maxLength={4000} onChange={(e) => setNote(e.target.value)} />
            </Field>
          </div>
          <ErrorNote message={error} />
          <div><button type="button" className="police-mini" disabled={busy} onClick={() => void save()}>Save</button></div>
        </div>
      </details>
    </>
  );
}
