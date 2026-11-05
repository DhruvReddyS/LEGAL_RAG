"use client";

import { Eye, FileOutput, FileSignature, FolderKanban, ListChecks, type LucideIcon } from "lucide-react";
import { useState } from "react";

import { CaseFileExport } from "@/components/police/CaseFileExport";
import { DeadlineRegister } from "@/components/police/DeadlineRegister";
import { DraftSet } from "@/components/police/DraftSet";
import { EvidenceCustody } from "@/components/police/EvidenceCustody";
import { OffenceElements } from "@/components/police/OffenceElements";
import { CaseDiary, RemandTracker } from "@/components/police/RemandDiary";
import { SearchCheck } from "@/components/police/SearchCheck";
import { SupervisorView, useMyUnits } from "@/components/police/SupervisorView";
import { WitnessTracker } from "@/components/police/WitnessTracker";
import { supervisedUnits } from "@/lib/police-presentation";

export type PoliceViewKey = "police_register" | "police_record" | "police_drafts" | "police_file" | "police_supervision";

export interface PoliceToolDef {
  key: PoliceViewKey;
  label: string;
  icon: LucideIcon;
  title: string;
  blurb: string;
  needsMatter: boolean;
}

const BASE: PoliceToolDef[] = [
  {
    key: "police_register",
    label: "Deadline register",
    icon: ListChecks,
    title: "Deadline register",
    blurb: "Every statutory limit across your open cases, most urgent first. Overdue means no completion is recorded; breached means the record shows it was late; a limit that cannot be computed says so.",
    needsMatter: false,
  },
  {
    key: "police_record",
    label: "Investigation record",
    icon: FolderKanban,
    title: "Investigation record",
    blurb: "Exhibits and custody, witnesses, searches, offence elements, remand and the case diary, for the case selected on the left.",
    needsMatter: true,
  },
  {
    key: "police_drafts",
    label: "Drafting set",
    icon: FileSignature,
    title: "Drafting set",
    blurb: "A s.35(3) notice, s.94 order, seizure memo, diary entry, remand application and chargesheet skeleton, filled from this case. Every one is a draft.",
    needsMatter: true,
  },
  {
    key: "police_file",
    label: "Court file",
    icon: FileOutput,
    title: "Case file for court",
    blurb: "This case's record in one printable document, for review before it goes anywhere.",
    needsMatter: true,
  },
];

const SUPERVISION: PoliceToolDef = {
  key: "police_supervision",
  label: "Unit view",
  icon: Eye,
  title: "Unit view",
  blurb: "Compliance and imminent breaches across the unit you supervise.",
  needsMatter: false,
};

export function isPoliceView(view: string): view is PoliceViewKey {
  return view.startsWith("police_");
}

/** The rail entries. The unit view appears only on a supervisor grant. */
export function usePoliceTools(enabled: boolean): { tools: PoliceToolDef[]; units: ReturnType<typeof useMyUnits> } {
  const units = useMyUnits(enabled);
  if (!enabled) return { tools: [], units };
  return { tools: supervisedUnits(units ?? []).length ? [...BASE, SUPERVISION] : BASE, units };
}

const TABS = [
  { key: "evidence", label: "Evidence & custody" },
  { key: "witnesses", label: "Witnesses" },
  { key: "search", label: "Search & seizure" },
  { key: "elements", label: "Offence elements" },
  { key: "remand", label: "Remand" },
  { key: "diary", label: "Case diary" },
] as const;

function InvestigationRecord({ caseId }: { caseId: string }) {
  const [tab, setTab] = useState<(typeof TABS)[number]["key"]>("evidence");
  return (
    <div className="police-stack">
      <div className="police-tabs" role="tablist" aria-label="Investigation record">
        {TABS.map((item) => (
          <button key={item.key} type="button" role="tab" aria-selected={tab === item.key} onClick={() => setTab(item.key)}>
            {item.label}
          </button>
        ))}
      </div>
      {tab === "evidence" && <EvidenceCustody caseId={caseId} />}
      {tab === "witnesses" && <WitnessTracker caseId={caseId} />}
      {tab === "search" && <SearchCheck caseId={caseId} />}
      {tab === "elements" && <OffenceElements caseId={caseId} />}
      {tab === "remand" && <RemandTracker caseId={caseId} />}
      {tab === "diary" && <CaseDiary caseId={caseId} />}
    </div>
  );
}

export function PoliceToolView({
  view,
  caseId,
  cases,
  units,
  onOpenCase,
}: {
  view: PoliceViewKey;
  caseId: string;
  cases: { id: string; title: string }[];
  units: ReturnType<typeof useMyUnits>;
  onOpenCase: (caseId: string) => void;
}) {
  switch (view) {
    case "police_register":
      return <DeadlineRegister cases={cases} onOpenCase={onOpenCase} />;
    case "police_record":
      return <InvestigationRecord key={caseId} caseId={caseId} />;
    case "police_drafts":
      return <DraftSet key={caseId} caseId={caseId} />;
    case "police_file":
      return <CaseFileExport key={caseId} caseId={caseId} />;
    case "police_supervision":
      return <SupervisorView units={units} />;
  }
}
