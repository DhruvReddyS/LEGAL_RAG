"use client";
import { Download, Phone, Printer } from "lucide-react";
import { useEffect, useState } from "react";
import { provision } from "@/lib/citizen-law/law";
import { HELP_NUMBERS, RIGHTS_TOPICS, type RightsTopic } from "@/lib/citizen-law/rights";
import { buildRightsHtml } from "@/lib/citizen-law/rights-export";
import { Cites, Disclaimer, downloadText } from "./shared";
import { useCitizenLang } from "./useCitizenLang";

type TopicId = RightsTopic["id"];

export default function RightsCard({ initialTopic }: { initialTopic?: TopicId }) {
  const { lang, t } = useCitizenLang();
  const [topicId, setTopicId] = useState<TopicId>(initialTopic ?? "arrest");
  useEffect(() => { if (initialTopic) setTopicId(initialTopic); }, [initialTopic]);
  const topic = RIGHTS_TOPICS.find(item => item.id === topicId) ?? RIGHTS_TOPICS[0];
  return <div className="ctz-rights">
    <p className="ctz-lead ctz-no-print">{t("rightsLead")}</p>
    <div className="ctz-actions ctz-no-print">
      <button type="button" className="ctz-btn" onClick={() => window.print()}><Printer size={15} aria-hidden="true"/>{t("print")}</button>
      <button type="button" className="ctz-btn ctz-btn-quiet" onClick={() => downloadText(`corpusil-rights-${lang}.html`, buildRightsHtml(lang), "text/html;charset=utf-8")}><Download size={15} aria-hidden="true"/>{t("saveCopy")}</button>
    </div>
    <section className="ctz-numbers" aria-label={t("numbersTitle")}>
      <h3>{t("numbersTitle")}</h3>
      <ul>{HELP_NUMBERS.map(item => <li key={item.number}><a href={`tel:${item.number}`}><Phone size={14} aria-hidden="true"/><strong>{item.number}</strong></a><span>{item.label[lang]}</span></li>)}</ul>
      <Cites ids={HELP_NUMBERS.map(item => item.cite)}/>
    </section>
    <div className="ctz-tabs ctz-no-print" role="tablist" aria-label={t("toolRights")}>
      {RIGHTS_TOPICS.map(item => <button key={item.id} type="button" role="tab" aria-selected={item.id === topic.id} onClick={() => setTopicId(item.id)}>{item.title[lang]}</button>)}
    </div>
    <section className="ctz-screen-only" role="tabpanel" aria-label={topic.title[lang]}>
      <h3 className="ctz-topic-title">{topic.title[lang]}</h3>
      <p className="ctz-topic-intro">{topic.intro[lang]}</p>
      <ol className="ctz-points">{topic.points.map(point => <li key={point.id}><p>{point.text[lang]}</p><Cites ids={point.cites}/></li>)}</ol>
    </section>
    {/* Print carries every topic, with its citations written out: details do not open on paper. */}
    <div className="ctz-print-only">
      {RIGHTS_TOPICS.map(item => <section key={item.id}>
        <h3>{item.title[lang]}</h3>
        <p>{item.intro[lang]}</p>
        <ol>{item.points.map(point => <li key={point.id}>{point.text[lang]} <small lang="en">({point.cites.map(id => provision(id).label).join("; ")})</small></li>)}</ol>
      </section>)}
    </div>
    <p className="ctz-note">{t("rightsLastChecked")}</p>
    <Disclaimer/>
  </div>;
}
