"use client";

import { CircleCheck, CircleDashed, CircleX, ClipboardCheck, Loader2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { getComplianceChecklist, recordCompliance } from "@/lib/api";
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
  ],
  search_and_seizure: [],
  case_diary: [],
  final_report: [
    ["is_listed_sexual_offence", "Offence is listed under s.193(2) — BNS ss.64–71"],
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
  satisfied: { label: "Done", Icon: CircleCheck, cls: "compliance-satisfied" },
  not_satisfied: { label: "Not done", Icon: CircleX, cls: "compliance-failed" },
  not_recorded: { label: "Not recorded", Icon: CircleDashed, cls: "compliance-unrecorded" },
};

export function ComplianceChecklist({ caseId }: { caseId: string }) {
  const [action, setAction] = useState<PoliceAction>("arrest");
  const [flags, setFlags] = useState<Record<string, boolean>>({
    arrested_person_is_woman: false,
    handcuffs_used: false,
    memorandum_attested_by_family: false,
    is_listed_sexual_offence: false,
    electronic_device_seized: false,
  });
  const [checklist, setChecklist] = useState<Checklist | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    if (!caseId) return;
    try {
      setChecklist(await getComplianceChecklist(caseId, action, flags));
      setNotice("");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not load the checklist.");
    }
  }, [caseId, action, flags]);

  useEffect(() => { void load(); }, [load]);

  const cycle = async (key: string) => {
    if (!checklist) return;
    const next: Record<string, ComplianceStatus> = {};
    for (const item of checklist.items) {
      const status = item.key === key ? CYCLE[item.status] : item.status;
      // Only confirmed states are sent. Omitting a key is how it returns to
      // not_recorded, which is how a mistaken tick is withdrawn.
      if (status !== "not_recorded") next[item.key] = status;
    }
    setBusy(true);
    try {
      setChecklist(await recordCompliance(caseId, action, next, flags));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not record that.");
    } finally {
      setBusy(false);
    }
  };

  if (!caseId) return <p className="text-xs text-[#827b8c]">Select a matter to review its compliance record.</p>;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="inline-flex rounded-lg bg-[#f1eee8] p-1">
          {ACTIONS.map(item => (
            <button
              key={item.value}
              onClick={() => setAction(item.value)}
              className={`rounded-md px-3 py-1.5 text-xs font-medium ${action === item.value ? "bg-white text-[#303039] shadow-sm" : "text-[#827b8c]"}`}
            >
              {item.label}
            </button>
          ))}
        </div>
        {busy && <Loader2 size={14} className="animate-spin text-[#897499]" />}
        {notice && <span className="text-xs text-[#b42318]">{notice}</span>}
      </div>

      {FLAGS_FOR[action].length > 0 && (
        <div className="flex flex-wrap gap-x-5 gap-y-2 text-xs text-[#54515d]">
          {FLAGS_FOR[action].map(([key, label]) => (
            <label key={key} className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={!!flags[key]}
                onChange={event => setFlags(current => ({ ...current, [key]: event.target.checked }))}
              />
              {label}
            </label>
          ))}
        </div>
      )}

      {checklist && (
        <>
          <div className="flex flex-wrap gap-2 text-[11px]">
            <span className="rounded-md bg-[#f1edf6] px-2 py-1 text-[#54515d]">{checklist.items.length} requirements</span>
            {checklist.outstanding.length > 0 && (
              <span className="rounded-md bg-[#fff5f4] px-2 py-1 font-medium text-[#b42318]">{checklist.outstanding.length} not done</span>
            )}
            {checklist.not_recorded.length > 0 && (
              <span className="rounded-md bg-[#faf7f2] px-2 py-1 font-medium text-[#8a5a12]">{checklist.not_recorded.length} not recorded</span>
            )}
          </div>

          <ul className="space-y-2">
            {checklist.items.map(item => {
              const shown = PRESENTATION[item.status];
              return (
                <li key={item.key} className={`rounded-xl border p-3.5 ${shown.cls}`}>
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
                        <p className="text-sm leading-5 text-[#54515d]">{item.requirement}</p>
                        <span className="shrink-0 rounded-md bg-white/70 px-1.5 py-0.5 font-mono text-[10px] text-[#897499]">{item.provision}</span>
                      </div>
                      <p className="mt-1.5 text-[11px] leading-4 text-[#75817b]">
                        {item.consequence}
                        {item.applies_because && <> Applies because {item.applies_because}.</>}
                      </p>
                    </div>
                    <span className="shrink-0 text-[10px] font-semibold uppercase tracking-wide">{shown.label}</span>
                  </div>
                </li>
              );
            })}
          </ul>
          <p className="text-[11px] leading-4 text-[#75817b]">
            &ldquo;Not recorded&rdquo; is not a finding either way — it means nobody has confirmed
            this requirement, which is a record to complete rather than a breach to remedy.
          </p>
        </>
      )}
    </div>
  );
}
