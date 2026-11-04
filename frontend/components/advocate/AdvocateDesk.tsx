"use client";

import { Archive, CalendarDays, FilePenLine, FileSearch, FileText, GitCompareArrows, History, MessagesSquare, Scale, ScanText } from "lucide-react";
import { useState, type ReactNode } from "react";

import BailTool from "./BailTool";
import BriefTool from "./BriefTool";
import CalendarTool from "./CalendarTool";
import DebateTool from "./DebateTool";
import DraftingTool from "./DraftingTool";
import { CompareTool, OpponentTool, PrecedentTool, TreatmentTool } from "./ResearchTools";
import SavedWork from "./SavedWork";
import { NeedsCase } from "./shared";

type DeskTool = "bail" | "drafts" | "calendar" | "brief" | "debate" | "precedents" | "treatment" | "opponent" | "compare" | "saved";

const GROUPS: { label: string; tools: { key: DeskTool; label: string; icon: typeof Scale }[] }[] = [
  {
    label: "Prepare",
    tools: [
      { key: "bail", label: "Bail", icon: Scale },
      { key: "drafts", label: "Drafting", icon: FilePenLine },
      { key: "calendar", label: "Calendar", icon: CalendarDays },
      { key: "brief", label: "Brief", icon: FileText },
      { key: "debate", label: "Debate room", icon: MessagesSquare },
    ],
  },
  {
    label: "Judgments held",
    tools: [
      { key: "precedents", label: "Precedents", icon: FileSearch },
      { key: "treatment", label: "Treatment check", icon: History },
      { key: "opponent", label: "Opponent’s authorities", icon: ScanText },
      { key: "compare", label: "Compare on facts", icon: GitCompareArrows },
    ],
  },
  { label: "Kept", tools: [{ key: "saved", label: "Saved work", icon: Archive }] },
];

/** Mounted with the case id as its key, so nothing from one case can show under another. */
export default function AdvocateDesk({ caseId, caseTitle }: { caseId: string; caseTitle?: string }) {
  const [tool, setTool] = useState<DeskTool>("bail");
  const needsCase = (body: ReactNode) => (caseId ? body : <NeedsCase />);
  return (
    <div className="adv-desk">
      <nav className="adv-tabs" aria-label="Advocate tools">
        {GROUPS.map((group) => (
          <div key={group.label} className="adv-tab-group" role="group" aria-label={group.label}>
            {group.tools.map((item) => (
              <button
                key={item.key}
                type="button"
                className="adv-tab"
                aria-current={tool === item.key ? "page" : undefined}
                onClick={() => setTool(item.key)}
              >
                <item.icon size={14} aria-hidden="true" />{item.label}
              </button>
            ))}
          </div>
        ))}
      </nav>
      {tool === "bail" && needsCase(<BailTool caseId={caseId} />)}
      {tool === "drafts" && needsCase(<DraftingTool caseId={caseId} />)}
      {tool === "calendar" && <CalendarTool caseId={caseId} caseTitle={caseTitle} />}
      {tool === "brief" && needsCase(<BriefTool caseId={caseId} />)}
      {tool === "debate" && needsCase(<DebateTool caseId={caseId} />)}
      {tool === "precedents" && <PrecedentTool />}
      {tool === "treatment" && <TreatmentTool />}
      {tool === "opponent" && needsCase(<OpponentTool caseId={caseId} />)}
      {tool === "compare" && needsCase(<CompareTool caseId={caseId} />)}
      {tool === "saved" && needsCase(<SavedWork caseId={caseId} />)}
    </div>
  );
}
