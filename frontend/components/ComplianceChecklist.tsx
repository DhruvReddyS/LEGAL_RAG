"use client";

import { CircleCheck, CircleDashed, CircleX, ClipboardCheck, Loader2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { ComplianceRecordForm } from "@/components/police/ComplianceRecordForm";
import { getComplianceChecklist, recordCompliance } from "@/lib/api";
import { getComplianceRecords, listEvidence } from "@/lib/api-police";
import type { ComplianceRecordItem, EvidenceItem } from "@/lib/types-police";
import type { ComplianceChecklist as Checklist, ComplianceStatus, PoliceAction } from "@/lib/types";

const ACTIONS: { value: PoliceAction; label: string }[] = [
  { value: "arrest", label: "Arrest" },
  { value: "search_and_seizure", label: "Search & seizure" },
  { value: "case_diary", label: "Case diary" },
  { value: "final_report", label: "Final report" },
];

/** Which conditional flags change the list, per action. Showing a flag that
 *  changes nothing invites the user to believe it did. */
const FLAGS_FOR: Record<PoliceAction, readonly (readonly [string, string])[]> = {
  arrest: [
    ["arrested_person_is_woman", "Arrested person is a woman"],
    ["handcuffs_used", "Handcuffs were used"],
    ["memorandum_attested_by_family", "Memorandum attested by a family member"],
    ["bailable_arrest_without_warrant", "Arrest without warrant, offence bailable"],
  ],
  search_and_seizure: [],
  case_diary: [],
  final_report: [
    ["is_listed_sexual_offence", "Clause (h) offence: BNS ss.64–68, 70 or 71. Not s.69, and not a POCSO offence on its own"],
    ["electronic_device_seized", "An electronic device was seized"],
  ],
};

/**
 * Three states, not a checkbox.
 *
 * A checkbox has two, and collapsing "nobody recorded this" into "not done"
 * makes a complete investigation look unlawful, while collapsing it into
 * "done" certifies one nobody checked. The API keeps them apart and so does
 * this: unrecorded is the default and reads as neither.
 */
const CYCLE: Record<ComplianceStatus, ComplianceStatus> = {
  not_recorded: "satisfied",
  satisfied: "not_satisfied",
  not_satisfied: "not_recorded",
};

const PRESENTATION: Record<ComplianceStatus, { label: string; Icon: typeof CircleCheck; cls: string }> = {
  satisfied: { label: "Done", Icon: CircleCheck, cls: "state-ok" },
  not_satisfied: { label: "Not done", Icon: CircleX, cls: "state-bad" },
  not_recorded: { label: "Not recorded", Icon: CircleDashed, cls: "state-warn" },
};

export function ComplianceChecklist({ caseId }: { caseId: string }) {
  const [action, setAction] = useState<PoliceAction>("arrest");
  const [checklist, setChecklist] = useState<Checklist | null>(null);
  const [records, setRecords] = useState<Record<string, ComplianceRecordItem>>({});
  const [evidence, setEvidence] = useState<EvidenceItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  // The flags are on the record, so a reload lists the same rows. Nothing is sent
  // until the first read has said what they are: a save from the defaults would
  // switch them off.
  const flags = checklist?.flags ?? {};

  const loadRecords = useCallback(async () => {
    try {
      const response = await getComplianceRecords(caseId, action);
      setRecords(Object.fromEntries(response.items.map((item) => [item.key, item])));
    } catch {
      setRecords({});
    }
  }, [caseId, action]);

  const load = useCallback(async () => {
    if (!caseId) return;
    try {
      setChecklist(await getComplianceChecklist(caseId, action));
      setNotice("");
    } catch (error) {
      // A failed read must not leave the last action's rows showing under this one.
      setChecklist(null);
      setNotice(error instanceof Error ? error.message : "Could not load the checklist.");
    }
    void loadRecords();
  }, [caseId, action, loadRecords]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => { if (caseId) listEvidence(caseId).then(setEvidence).catch(() => setEvidence([])); }, [caseId]);

  const save = async (next: Record<string, ComplianceStatus>, nextFlags: Record<string, boolean>) => {
    setBusy(true);
    try {
      setChecklist(await recordCompliance(caseId, action, next, nextFlags));
      setNotice("");
      await loadRecords();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not record that.");
    } finally {
      setBusy(false);
    }
  };

  const currentStatus = () => {
    const out: Record<string, ComplianceStatus> = {};
    for (const item of checklist?.items ?? []) if (item.status !== "not_recorded") out[item.key] = item.status;
    return out;
  };

  const cycle = async (key: string) => {
    if (!checklist) return;
    const next = currentStatus();
    const moved = CYCLE[checklist.items.find((item) => item.key === key)?.status ?? "not_recorded"];
    // Only confirmed states are sent. Omitting a key is how it returns to
    // not_recorded, which is how a mistaken tick is withdrawn.
    if (moved === "not_recorded") delete next[key];
    else next[key] = moved;
    await save(next, checklist.flags);
  };

  const toggleFlag = async (key: string, value: boolean) => {
    if (!checklist) return;
    await save(currentStatus(), { ...checklist.flags, [key]: value });
  };

  if (!caseId) return <p className="state-hint">Select a case to review its compliance record.</p>;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="inline-flex rounded-lg bg-[var(--hover)] p-1">
          {ACTIONS.map(item => (
            <button
              key={item.value}
              onClick={() => setAction(item.value)}
              className={`rounded-md px-3 py-1.5 text-xs font-medium ${action === item.value ? "bg-[var(--card)] text-[var(--ink)] shadow-sm" : "text-[var(--ink-soft)]"}`}
            >
              {item.label}
            </button>
          ))}
        </div>
        {busy && <Loader2 size={14} className="animate-spin text-[var(--accent)]" />}
        {notice && <span className="text-xs text-[var(--state-bad-text)]">{notice}</span>}
      </div>

      {FLAGS_FOR[action].length > 0 && (
        <div className="flex flex-wrap gap-x-5 gap-y-2 text-xs text-[var(--ink)]">
          {FLAGS_FOR[action].map(([key, label]) => (
            <label key={key} className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={!!flags[key]}
                disabled={busy || !checklist}
                onChange={event => void toggleFlag(key, event.target.checked)}
              />
              {label}
            </label>
          ))}
        </div>
      )}

      {checklist && (
        <>
          <div className="flex flex-wrap gap-2 text-xs">
            <span className="state-tally is-plain">{checklist.items.length} requirements</span>
            {checklist.outstanding.length > 0 && (
              <span className="state-tally is-bad">{checklist.outstanding.length} not done</span>
            )}
            {checklist.not_recorded.length > 0 && (
              <span className="state-tally is-warn">{checklist.not_recorded.length} not recorded</span>
            )}
          </div>

          <ul className="space-y-2">
            {checklist.items.map(item => {
              const shown = PRESENTATION[item.status];
              return (
                <li key={item.key} className={`state-row ${shown.cls}`}>
                  <div className="flex items-start gap-3">
                    <button
                      onClick={() => cycle(item.key)}
                      disabled={busy}
                      aria-label={`${item.requirement} — currently ${shown.label}. Change.`}
                      className="mt-0.5 shrink-0 disabled:opacity-40"
                    >
                      <shown.Icon size={18} />
                    </button>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                        <p className="state-row-title">{item.requirement}</p>
                        <span className="provision-tag">{item.provision}</span>
                      </div>
                      <p className="state-row-detail">
                        {item.consequence}
                        {item.applies_because && <> Applies because {item.applies_because}.</>}
                      </p>
                      <ComplianceRecordForm caseId={caseId} action={action} record={records[item.key]} evidence={evidence} onSaved={() => void loadRecords()} />
                    </div>
                    <span className="state-row-status">{shown.label}</span>
                  </div>
                </li>
              );
            })}
          </ul>
          <p className="state-hint">
            &ldquo;Not recorded&rdquo; is not a finding either way — it means nobody has confirmed
            this requirement, which is a record to complete rather than a breach to remedy.
          </p>
        </>
      )}
    </div>
  );
}
