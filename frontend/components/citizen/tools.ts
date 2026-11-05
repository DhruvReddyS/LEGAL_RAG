import { BookOpenCheck, CalendarDays, Compass, FilePenLine, FileSearch, HandHeart, Route, type LucideIcon } from "lucide-react";
import type { UiKey } from "@/lib/citizen-i18n";

export type CitizenTool = "journeys" | "rights" | "router" | "notice" | "draft" | "legal-aid" | "matter";

/** Apart from the workspace, so the sidebar can list them without loading the tools. */
export const CITIZEN_TOOLS: { id: CitizenTool; icon: LucideIcon; title: UiKey; blurb: UiKey }[] = [
  { id: "journeys", icon: Compass, title: "toolJourneys", blurb: "toolJourneysBlurb" },
  { id: "rights", icon: BookOpenCheck, title: "toolRights", blurb: "toolRightsBlurb" },
  { id: "router", icon: Route, title: "toolRouter", blurb: "toolRouterBlurb" },
  { id: "notice", icon: FileSearch, title: "toolNotice", blurb: "toolNoticeBlurb" },
  { id: "draft", icon: FilePenLine, title: "toolDraft", blurb: "toolDraftBlurb" },
  { id: "legal-aid", icon: HandHeart, title: "toolLegalAid", blurb: "toolLegalAidBlurb" },
  { id: "matter", icon: CalendarDays, title: "toolMatter", blurb: "toolMatterBlurb" },
];
