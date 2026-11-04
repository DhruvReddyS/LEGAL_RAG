"use client";
import { ArrowLeft, ArrowRight, BookOpenCheck, CalendarDays, Compass, FilePenLine, FileSearch, HandHeart, Route, type LucideIcon } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { listDeadlines } from "@/lib/api-citizen";
import { formatDate, type UiKey } from "@/lib/citizen-i18n";
import type { ToolLink } from "@/lib/citizen-law/journeys";
import { needsAttention } from "@/lib/citizen-matter";
import type { CitizenDeadline, DeadlineDraft } from "@/lib/types-citizen";
import DraftBuilder from "./DraftBuilder";
import ForumRouter from "./ForumRouter";
import JourneyFlow from "./JourneyFlow";
import LegalAidCheck from "./LegalAidCheck";
import MyMatter from "./MyMatter";
import NoticeExplainer from "./NoticeExplainer";
import RightsCard from "./RightsCard";
import { Disclaimer, LangSwitcher } from "./shared";
import { useCitizenLang } from "./useCitizenLang";

export type CitizenTool = "journeys" | "rights" | "router" | "notice" | "draft" | "legal-aid" | "matter";

export const CITIZEN_TOOLS: { id: CitizenTool; icon: LucideIcon; title: UiKey; blurb: UiKey }[] = [
  { id: "journeys", icon: Compass, title: "toolJourneys", blurb: "toolJourneysBlurb" },
  { id: "rights", icon: BookOpenCheck, title: "toolRights", blurb: "toolRightsBlurb" },
  { id: "router", icon: Route, title: "toolRouter", blurb: "toolRouterBlurb" },
  { id: "notice", icon: FileSearch, title: "toolNotice", blurb: "toolNoticeBlurb" },
  { id: "draft", icon: FilePenLine, title: "toolDraft", blurb: "toolDraftBlurb" },
  { id: "legal-aid", icon: HandHeart, title: "toolLegalAid", blurb: "toolLegalAidBlurb" },
  { id: "matter", icon: CalendarDays, title: "toolMatter", blurb: "toolMatterBlurb" },
];

type Open = { tool: CitizenTool | null; arg?: string; draft?: DeadlineDraft | null };

/** The citizen's tools. Mounted from page.tsx, with `/` left as it was. */
export default function CitizenWorkspace({ requested, onAsk }: { requested: { tool: CitizenTool | null; nonce: number } | null; onAsk: (question: string) => void }) {
  const { lang, t } = useCitizenLang();
  const [open, setOpen] = useState<Open>({ tool: requested?.tool ?? null });
  const [attention, setAttention] = useState<CitizenDeadline[]>([]);
  useEffect(() => { if (requested) { setOpen({ tool: requested.tool }); window.scrollTo({ top: 0 }); } }, [requested]);
  useEffect(() => { listDeadlines().then(response => setAttention(needsAttention(response.items))).catch(() => setAttention([])); }, []);
  const onDeadlines = useCallback((items: CitizenDeadline[]) => setAttention(needsAttention(items)), []);

  const go = (next: Open) => { setOpen(next); window.scrollTo({ top: 0 }); };
  const onLegalAid = () => go({ tool: "legal-aid" });
  const onRecord = (draft: DeadlineDraft) => go({ tool: "matter", draft });
  const onTool = (link: ToolLink) => {
    if (link.tool === "rights") go({ tool: "rights", arg: link.topic });
    else if (link.tool === "router") go({ tool: "router", arg: link.situation });
    else if (link.tool === "draft") go({ tool: "draft", arg: link.template });
    else go({ tool: link.tool });
  };
  const current = CITIZEN_TOOLS.find(item => item.id === open.tool);

  return <section className="ctz-workspace" aria-label={t("toolsTitle")}>
    <header className="ctz-head ctz-no-print">
      <div>
        {current ? <button type="button" className="ctz-link ctz-head-back" onClick={() => go({ tool: null })}><ArrowLeft size={14} aria-hidden="true"/>{t("back")}</button> : null}
        <h1>{current ? t(current.title) : t("toolsTitle")}</h1>
      </div>
      <LangSwitcher/>
    </header>
    {!current && <>
      <p className="ctz-lead">{t("toolsIntro")}</p>
      {!!attention.length && <section className="ctz-attention" aria-label={t("attentionTitle")}>
        <h2><CalendarDays size={16} aria-hidden="true"/>{t("attentionTitle")}</h2>
        <ul>{attention.slice(0, 4).map(item => <li key={item.id} data-status={item.status}><button type="button" onClick={() => go({ tool: "matter" })}><span>{item.title}</span><b>{formatDate(item.due_on, lang)}</b></button></li>)}</ul>
      </section>}
      <ul className="ctz-grid">{CITIZEN_TOOLS.map(tool => <li key={tool.id}><button type="button" onClick={() => go({ tool: tool.id })}><tool.icon size={20} strokeWidth={1.6} aria-hidden="true"/><strong>{t(tool.title)}</strong><span>{t(tool.blurb)}</span><ArrowRight size={15} className="ctz-grid-arrow" aria-hidden="true"/></button></li>)}</ul>
      <p className="ctz-note">{t("chatStaysEnglish")}</p>
      <Disclaimer/>
    </>}
    {open.tool === "journeys" && <JourneyFlow key={open.arg ?? "all"} initialJourney={open.arg} onAsk={onAsk} onTool={onTool}/>}
    {open.tool === "rights" && <RightsCard initialTopic={open.arg as "arrest" | undefined}/>}
    {open.tool === "router" && <ForumRouter key={open.arg ?? "all"} initialSituation={open.arg} onRecord={onRecord} onLegalAid={onLegalAid}/>}
    {open.tool === "notice" && <NoticeExplainer onRecord={onRecord} onLegalAid={onLegalAid}/>}
    {open.tool === "draft" && <DraftBuilder key={open.arg ?? "all"} initialTemplate={open.arg}/>}
    {open.tool === "legal-aid" && <LegalAidCheck/>}
    {open.tool === "matter" && <MyMatter draft={open.draft} onChange={onDeadlines}/>}
  </section>;
}
