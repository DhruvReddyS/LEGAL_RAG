"use client";

import { ArrowRight } from "lucide-react";
import { SITE_ROUTES } from "@/lib/site";
import type { ProRoute } from "@/lib/pro-route";
import { Card, PageHead, ProLink, usePro } from "./context";

export default function HelpScreen() {
  const { isPolice, noun, nounPlural } = usePro();
  const sections: { to: ProRoute; title: string; body: string }[] = [
    { to: { section: "dashboard" }, title: "Dashboard", body: isPolice ? "What is overdue or expiring across your investigations, and where to act on it." : "Your next hearings and limitation dates, and what is overdue, across your cases." },
    { to: { section: "cases" }, title: nounPlural, body: `Every ${noun}, with search and filters. Opening one gives it a page of its own, and nothing from it appears under another.` },
    { to: { section: "deadlines" }, title: isPolice ? "Deadlines" : "Calendar", body: isPolice ? "The register of statutory limits across your open investigations." : "Every date you have recorded across your cases." },
    { to: { section: "drafts" }, title: "Drafts", body: `Everything drafted across your open ${noun}s. Each one opens in its own ${noun}.` },
    { to: { section: "research" }, title: "Research", body: `Questions about the law only. These chats read no ${noun} files.` },
    { to: { section: "law" }, title: "Law lookup", body: "Open a provision by its citation, and see what it replaced or became." },
  ];
  const caseTabs = isPolice
    ? [["Overview", "Where the investigation stands, and the next steps."], ["Timeline", "Dates stated in its files, in order."], ["Files and evidence", "Uploads, exhibits, custody, witnesses, search and seizure."], ["Deadlines and compliance", "Time limits, compliance record, remand and case diary."], ["Drafts", "FIR draft, drafting set and the case file for court."], ["Tools", "Offence elements, citation check and authority search."], ["Ask", "A chat that may read the law and this investigation's files."]]
    : [["Overview", "Where the case stands, and the work kept so far."], ["Timeline", "Dates stated in its files, in order."], ["Files", "Uploads, and reading what was indexed."], ["Dates", "Hearings, limitation dates and the limitation calculator."], ["Strategy", "Defence analysis, bail and the debate room."], ["Authorities", "Precedents, treatment, the opponent's citations and citation checks."], ["Drafts", "Drafting, briefs and saved work."], ["Ask", "A chat that may read the law and this case's files."]];
  return (
    <div className="pro-page">
      <PageHead title="Help" lead="How this workspace is arranged, and where each job lives." />
      <div className="pro-dash">
        <div className="pro-dash-main">
          <Card title="Sections" id="help-sections">
            <ul className="pro-rows">
              {sections.map((item) => (
                <li key={item.title}>
                  <ProLink to={item.to} className="pro-activity">
                    <span className="pro-due-main pro-wrap"><strong>{item.title}</strong><span className="pro-meta"><span>{item.body}</span></span></span>
                    <ArrowRight size={14} aria-hidden="true" className="flex-none" />
                  </ProLink>
                </li>
              ))}
            </ul>
          </Card>
          <Card title={`Inside a ${noun}`} id="help-case">
            <dl className="pro-defs">
              {caseTabs.map(([term, detail]) => <div key={term}><dt>{term}</dt><dd>{detail}</dd></div>)}
            </dl>
          </Card>
        </div>
        <div className="pro-dash-side">
          <Card title="What to keep in mind" id="help-keep">
            <ul className="pro-plain">
              <li>This is information for your own review, not legal advice. Check each source before you rely on it.</li>
              <li>Every draft stays a draft until you have reviewed it.</li>
              <li>A date nobody has entered produces a stated unknown, not an estimate.</li>
              <li>Your {noun}s are yours alone. A chat inside one reads that {noun} and no other.</li>
            </ul>
          </Card>
          <Card title="More" id="help-more">
            <ul className="pro-plain">
              <li><a className="pro-text-link" href={SITE_ROUTES.help}>Full help pages</a></li>
              <li><a className="pro-text-link" href={SITE_ROUTES.privacy}>Privacy</a></li>
            </ul>
          </Card>
        </div>
      </div>
    </div>
  );
}
