"use client";

import { CalendarClock, CalendarRange, FileText, FolderOpen, LayoutGrid, MessageSquare, NotebookPen, Scale, ScrollText, Wrench, type LucideIcon } from "lucide-react";
import dynamic from "next/dynamic";
import type { ReactNode } from "react";
import type { DefenceAnalysisResponse } from "@/lib/types";
import { RowsLoading } from "../context";
import CaseInsights from "@/components/case/CaseInsights";
import { CaseNotesPanel } from "./slots";

const Loading = () => <RowsLoading label="Loading" />;
const lazy = dynamic;

// Every tool is its own chunk. Nobody pays for a screen they do not open.
const CaseChronology = lazy(() => import("@/components/CaseChronology"), { loading: Loading });
const InvestigationTimeline = lazy(() => import("@/components/InvestigationTimeline").then((m) => m.InvestigationTimeline), { loading: Loading });
const ComplianceChecklist = lazy(() => import("@/components/ComplianceChecklist").then((m) => m.ComplianceChecklist), { loading: Loading });
const AuthorityCheck = lazy(() => import("@/components/AuthorityCheck").then((m) => m.AuthorityCheck), { loading: Loading });
const DocumentAnalyzerWorkspace = lazy(() => import("@/components/DocumentAnalyzerWorkspace"), { loading: Loading });
const EvidenceCustody = lazy(() => import("@/components/police/EvidenceCustody").then((m) => m.EvidenceCustody), { loading: Loading });
const WitnessTracker = lazy(() => import("@/components/police/WitnessTracker").then((m) => m.WitnessTracker), { loading: Loading });
const SearchCheck = lazy(() => import("@/components/police/SearchCheck").then((m) => m.SearchCheck), { loading: Loading });
const OffenceElements = lazy(() => import("@/components/police/OffenceElements").then((m) => m.OffenceElements), { loading: Loading });
const RemandTracker = lazy(() => import("@/components/police/RemandDiary").then((m) => m.RemandTracker), { loading: Loading });
const CaseDiary = lazy(() => import("@/components/police/RemandDiary").then((m) => m.CaseDiary), { loading: Loading });
const DraftSet = lazy(() => import("@/components/police/DraftSet").then((m) => m.DraftSet), { loading: Loading });
const CaseFileExport = lazy(() => import("@/components/police/CaseFileExport").then((m) => m.CaseFileExport), { loading: Loading });
const BailTool = lazy(() => import("@/components/advocate/BailTool"), { loading: Loading });
const BriefTool = lazy(() => import("@/components/advocate/BriefTool"), { loading: Loading });
const CalendarTool = lazy(() => import("@/components/advocate/CalendarTool"), { loading: Loading });
const DebateTool = lazy(() => import("@/components/advocate/DebateTool"), { loading: Loading });
const DraftingTool = lazy(() => import("@/components/advocate/DraftingTool"), { loading: Loading });
const SavedWork = lazy(() => import("@/components/advocate/SavedWork"), { loading: Loading });
const PrecedentTool = lazy(() => import("@/components/advocate/ResearchTools").then((m) => m.PrecedentTool), { loading: Loading });
const TreatmentTool = lazy(() => import("@/components/advocate/ResearchTools").then((m) => m.TreatmentTool), { loading: Loading });
const OpponentTool = lazy(() => import("@/components/advocate/ResearchTools").then((m) => m.OpponentTool), { loading: Loading });
const CompareTool = lazy(() => import("@/components/advocate/ResearchTools").then((m) => m.CompareTool), { loading: Loading });
const FirDraftPanel = lazy(() => import("./panels").then((m) => m.FirDraftPanel), { loading: Loading });
const DefencePanel = lazy(() => import("./panels").then((m) => m.DefencePanel), { loading: Loading });
const AuthoritySearch = lazy(() => import("./panels").then((m) => m.AuthoritySearch), { loading: Loading });
const CaseFilesPanel = lazy(() => import("./panels").then((m) => m.CaseFilesPanel), { loading: Loading });

export interface CaseToolContext {
  caseId: string;
  caseTitle: string;
  isPolice: boolean;
  role: string;
  /** Bumped when a file or a draft changes, so anything counting them reads again. */
  refresh: number;
  changed: () => void;
  datesChanged: () => void;
  go: (tab: string, tool?: string) => void;
  openedAnalysis: DefenceAnalysisResponse | null;
}

export interface CaseTool {
  key: string;
  label: string;
  /** A short group heading in the tool list, where a tab has more than a few. */
  group?: string;
  title: string;
  blurb: string;
  render: (ctx: CaseToolContext) => ReactNode;
}

export interface CaseTab {
  key: string;
  label: string;
  icon: LucideIcon;
  /** Overview and Ask are drawn by the case page itself. */
  tools: CaseTool[];
}

const timelineTool: CaseTool = {
  key: "chronology",
  label: "Timeline",
  title: "What happened when",
  blurb: "Every date stated in this case's files, in order, each with its file and page.",
  render: ({ caseId, go }) => <CaseChronology caseId={caseId} onOpenDocuments={() => go("files")} />,
};

const insightsTool: CaseTool = {
  key: "insights",
  label: "People and contradictions",
  title: "Read across the files",
  blurb: "Who is named in this case, and where its statements disagree, each quoted from the files.",
  render: ({ caseId }) => <CaseInsights caseId={caseId} />,
};

const filesTool: CaseTool = {
  key: "files",
  label: "Files",
  group: "Files",
  title: "Files in this case",
  blurb: "Uploaded files are read and made searchable for this case alone. No other case, and nobody else, can read them.",
  render: ({ caseId, isPolice, refresh, changed, go }) => <CaseFilesPanel caseId={caseId} isPolice={isPolice} refresh={refresh} onChanged={changed} onReview={() => go("files", "review")} />,
};

const reviewTool: CaseTool = {
  key: "review",
  label: "Review documents",
  group: "Files",
  title: "Review documents",
  blurb: "Read what was indexed for this case, with the passage, its pages and its current-law status.",
  render: ({ caseId, role, refresh }) => <DocumentAnalyzerWorkspace caseId={caseId} role={role} refreshToken={refresh} />,
};

const citationsTool = (group?: string): CaseTool => ({
  key: "citations",
  label: "Check citations",
  group,
  title: "Check citations",
  blurb: "Paste a draft. Every provision it cites is checked against the official concordance. No model reads the text.",
  render: ({ caseId }) => <AuthorityCheck caseId={caseId} />,
});

const searchTool = (group?: string): CaseTool => ({
  key: "search",
  label: "Find authority",
  group,
  title: "Find authority",
  blurb: "Search the law and this case's files. Results never cross into another person's case.",
  render: ({ caseId }) => <AuthoritySearch caseId={caseId} />,
});

/** An investigating officer works from the record outward: evidence, limits, papers for court. */
const POLICE_TABS: CaseTab[] = [
  { key: "overview", label: "Overview", icon: LayoutGrid, tools: [] },
  { key: "timeline", label: "Timeline and people", icon: CalendarRange, tools: [timelineTool, insightsTool] },
  {
    key: "files",
    label: "Files and evidence",
    icon: FolderOpen,
    tools: [
      filesTool,
      reviewTool,
      { key: "exhibits", label: "Exhibits and custody", group: "Record", title: "Exhibits and chain of custody", blurb: "Every item seized, where it has been and who held it.", render: ({ caseId }) => <EvidenceCustody caseId={caseId} /> },
      { key: "witnesses", label: "Witnesses", group: "Record", title: "Witnesses", blurb: "Who has been examined, and what is still outstanding.", render: ({ caseId }) => <WitnessTracker caseId={caseId} /> },
      { key: "seizure", label: "Search and seizure", group: "Record", title: "Search and seizure", blurb: "Check a search or seizure against the record for it.", render: ({ caseId }) => <SearchCheck caseId={caseId} /> },
    ],
  },
  {
    key: "deadlines",
    label: "Deadlines and compliance",
    icon: CalendarClock,
    tools: [
      { key: "limits", label: "Time limits", title: "Investigation time limits", blurb: "BNSS time limits, computed by date arithmetic rather than generated. A date left blank produces a stated unknown, never a guess.", render: ({ caseId, datesChanged }) => <InvestigationTimeline caseId={caseId} onSaved={datesChanged} /> },
      { key: "compliance", label: "Compliance", title: "BNSS compliance record", blurb: "What the Sanhita requires to be recorded for an arrest, a search, the case diary and the final report. Nothing is assumed done.", render: ({ caseId }) => <ComplianceChecklist caseId={caseId} /> },
      { key: "remand", label: "Remand", title: "Remand", blurb: "Remand periods on record for this case.", render: ({ caseId }) => <RemandTracker caseId={caseId} /> },
      { key: "diary", label: "Case diary", title: "Case diary", blurb: "Entries on record for this case, in order.", render: ({ caseId }) => <CaseDiary caseId={caseId} /> },
    ],
  },
  {
    key: "drafts",
    label: "Drafts",
    icon: FileText,
    tools: [
      { key: "fir", label: "FIR draft", title: "FIR draft", blurb: "Record known facts only. Unknown fields stay visibly incomplete, and every suggested provision is retrieved for your review.", render: ({ caseId, caseTitle, changed }) => <FirDraftPanel caseId={caseId} caseTitle={caseTitle} onChanged={changed} /> },
      { key: "set", label: "Drafting set", title: "Drafting set", blurb: "A s.35(3) notice, s.94 order, seizure memo, diary entry, remand application and chargesheet skeleton, filled from this case. Every one is a draft.", render: ({ caseId }) => <DraftSet caseId={caseId} /> },
      { key: "court-file", label: "Case file for court", title: "Case file for court", blurb: "This case's record in one printable document, for review before it goes anywhere.", render: ({ caseId }) => <CaseFileExport caseId={caseId} /> },
    ],
  },
  {
    key: "tools",
    label: "Tools",
    icon: Wrench,
    tools: [
      { key: "elements", label: "Offence elements", title: "Offence elements", blurb: "Set out what the evidence shows against each element of an offence.", render: ({ caseId }) => <OffenceElements caseId={caseId} /> },
      citationsTool(),
      searchTool(),
    ],
  },
  { key: "ask", label: "Ask", icon: MessageSquare, tools: [] },
];

/** An advocate works towards the next date: papers, dates, the argument, authorities, then the filing. */
const ADVOCATE_TABS: CaseTab[] = [
  { key: "overview", label: "Overview", icon: LayoutGrid, tools: [] },
  { key: "timeline", label: "Timeline and people", icon: CalendarRange, tools: [timelineTool, insightsTool] },
  { key: "files", label: "Files", icon: FolderOpen, tools: [filesTool, reviewTool] },
  {
    key: "dates",
    label: "Dates",
    icon: CalendarClock,
    tools: [{ key: "calendar", label: "Dates", title: "Hearings and limitation", blurb: "Hearings, limitation and filing dates for this case, and a limitation calculator. A wrong date can lose a case, so check what it computes.", render: ({ caseId, caseTitle }) => <CalendarTool caseId={caseId} caseTitle={caseTitle} showAcross={false} /> }],
  },
  {
    key: "strategy",
    label: "Strategy",
    icon: Scale,
    tools: [
      { key: "defence", label: "Defence analysis", title: "Defence analysis", blurb: "Analyse allegations, evidence and procedure from both sides. Unsupported or unsafe tactics are rejected before results are returned.", render: ({ caseId, openedAnalysis, changed }) => <DefencePanel caseId={caseId} opened={openedAnalysis} onChanged={changed} /> },
      { key: "bail", label: "Bail", title: "Bail", blurb: "Regular, anticipatory, default and s.479 undertrial release, worked through from this case.", render: ({ caseId }) => <BailTool caseId={caseId} /> },
      { key: "debate", label: "Debate room", title: "Debate room", blurb: "Test a proposition from both sides. This takes a while, and you can leave it running.", render: ({ caseId }) => <DebateTool caseId={caseId} /> },
    ],
  },
  {
    key: "authorities",
    label: "Authorities",
    icon: ScrollText,
    tools: [
      { key: "precedents", label: "Precedents", group: "Judgments held", title: "Precedents", blurb: "Search the judgments held by court, year and holding. Each result says how many were searched.", render: () => <PrecedentTool /> },
      { key: "treatment", label: "Treatment check", group: "Judgments held", title: "Treatment check", blurb: "What the judgments held say about a citation.", render: () => <TreatmentTool /> },
      { key: "opponent", label: "Opponent's authorities", group: "Judgments held", title: "Opponent's authorities", blurb: "Check what the other side has cited.", render: ({ caseId }) => <OpponentTool caseId={caseId} /> },
      { key: "compare", label: "Compare on facts", group: "Judgments held", title: "Compare on facts", blurb: "Set a judgment held against the facts of this case.", render: ({ caseId }) => <CompareTool caseId={caseId} /> },
      citationsTool("This case"),
      searchTool("This case"),
    ],
  },
  {
    key: "drafts",
    label: "Drafts",
    icon: FileText,
    tools: [
      { key: "drafting", label: "Drafting", title: "Drafting", blurb: "Draft from the library, with authorities inserted from retrieval, for your review.", render: ({ caseId }) => <DraftingTool caseId={caseId} /> },
      { key: "brief", label: "Brief", title: "Brief and synopsis", blurb: "A brief or synopsis from the files in this case.", render: ({ caseId }) => <BriefTool caseId={caseId} /> },
      { key: "saved", label: "Saved work", title: "Saved work", blurb: "Everything kept for this case, as it was written.", render: ({ caseId }) => <SavedWork caseId={caseId} /> },
    ],
  },
  { key: "ask", label: "Ask", icon: MessageSquare, tools: [] },
];

export function caseTabs(isPolice: boolean): CaseTab[] {
  const tabs = isPolice ? POLICE_TABS : ADVOCATE_TABS;
  if (!CaseNotesPanel) return tabs;
  const Notes = CaseNotesPanel;
  // NOTES SLOT: appears on both roles as soon as ./slots.tsx names the component.
  const notes: CaseTab = {
    key: "notes",
    label: "Notes",
    icon: NotebookPen,
    tools: [{ key: "notes", label: "Notes", title: "Notes", blurb: "Your own notes on this case.", render: ({ caseId }) => <Notes key={caseId} caseId={caseId} /> }],
  };
  return [...tabs.slice(0, -1), notes, tabs[tabs.length - 1]];
}
