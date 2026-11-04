"use client";
import { ArrowLeft, ArrowRight, CalendarPlus, CircleAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { computeDeadline, isPast, routeSituation, SITUATIONS, type Answer, type DeadlineRule } from "@/lib/citizen-law/forums";
import { provision } from "@/lib/citizen-law/law";
import type { DeadlineDraft } from "@/lib/types-citizen";
import { Cites, Disclaimer, HumanRoute } from "./shared";
import { useCitizenLang } from "./useCitizenLang";

function RuleCard({ rule, onRecord }: { rule: DeadlineRule; onRecord: (draft: DeadlineDraft) => void }) {
  const { lang, t } = useCitizenLang();
  const [from, setFrom] = useState("");
  const due = from ? computeDeadline(rule, from) : null;
  const today = new Date().toISOString().slice(0, 10);
  const inputId = `from-${rule.id}`;
  return <li className="ctz-rule">
    <h4>{rule.label[lang]}</h4>
    <label className="ctz-field" htmlFor={inputId}><span>{rule.fromLabel[lang]}</span><input id={inputId} className="field" type="date" value={from} max="2100-12-31" onChange={event => setFrom(event.target.value)}/></label>
    {due ? <div className={`ctz-due ${isPast(due, today) ? "is-past" : ""}`} role="status">
      <span>{t("lastDay")}</span><strong>{due}</strong>
      {isPast(due, today) && <p><CircleAlert size={14} aria-hidden="true"/>{t("datePassed")}</p>}
      <button type="button" className="ctz-link" onClick={() => onRecord({ title: rule.label.en, due_on: due, source: "router", provision_label: provision(rule.cites[rule.cites.length - 1]).label })}><CalendarPlus size={14} aria-hidden="true"/>{t("addToMatter")}</button>
    </div> : <p className="ctz-note">{t("enterDate")}</p>}
    <Cites ids={rule.cites}/>
    {rule.extensionNote && <><p className="ctz-note">{rule.extensionNote[lang]}</p><Cites ids={rule.extensionCites ?? []}/></>}
  </li>;
}

export default function ForumRouter({ initialSituation, onRecord, onLegalAid }: { initialSituation?: string; onRecord: (draft: DeadlineDraft) => void; onLegalAid: () => void }) {
  const { lang, t } = useCitizenLang();
  const [situationId, setSituationId] = useState<string | null>(initialSituation ?? null);
  const [picked, setPicked] = useState(Boolean(initialSituation));
  const [answers, setAnswers] = useState<Record<string, Answer>>({});
  useEffect(() => { if (initialSituation) { setSituationId(initialSituation); setPicked(true); setAnswers({}); } }, [initialSituation]);
  const reset = () => { setSituationId(null); setPicked(false); setAnswers({}); };

  if (!picked) return <div>
    <p className="ctz-lead">{t("routerLead")}</p>
    <h3 className="ctz-section-title">{t("routerPick")}</h3>
    <ul className="ctz-choice-list">
      {SITUATIONS.map(item => <li key={item.id}><button type="button" onClick={() => { setSituationId(item.id); setPicked(true); setAnswers({}); }}><span><strong>{item.title[lang]}</strong><small lang="en">{item.blurb.en}</small></span><ArrowRight size={16} aria-hidden="true"/></button></li>)}
      <li><button type="button" onClick={() => { setSituationId(null); setPicked(true); }}><span><strong>{t("routerOther")}</strong></span><ArrowRight size={16} aria-hidden="true"/></button></li>
    </ul>
    <Disclaimer/>
  </div>;

  const result = routeSituation(situationId, answers);
  const backRow = <div className="ctz-actions ctz-step-nav"><button type="button" className="ctz-link" onClick={reset}><ArrowLeft size={14} aria-hidden="true"/>{t("routerPick")}</button></div>;

  if (result.status === "questions") return <div>
    <p className="ctz-journey-name">{result.situation.title[lang]}</p>
    <section className="ctz-step" aria-live="polite">
      <h3>{result.next.text[lang]}</h3>
      <div className="ctz-options is-row">
        {(["yes", "no", "unsure"] as Answer[]).map(answer => <button type="button" key={answer} className="ctz-option" onClick={() => setAnswers(current => ({ ...current, [result.next.id]: answer }))}>{answer === "yes" ? t("yes") : answer === "no" ? t("no") : t("notSure")}</button>)}
      </div>
    </section>
    {backRow}
  </div>;

  if (result.status === "abstain") return <div>
    {result.situation && <p className="ctz-journey-name">{result.situation.title[lang]}</p>}
    <section className="ctz-abstain" role="status">
      <h3>{t("weStopHere")}</h3>
      <p>{result.reason[lang]}</p>
      <Cites ids={result.cites}/>
    </section>
    <HumanRoute onLegalAid={onLegalAid}/>
    {!!result.situation?.notes.length && <section className="ctz-block"><h3>{t("alsoKnow")}</h3><ul className="ctz-notes">{result.situation.notes.map(note => <li key={note.text.en}><p>{note.text[lang]}</p><Cites ids={note.cites}/></li>)}</ul></section>}
    {backRow}
    <Disclaimer/>
  </div>;

  const { situation } = result;
  return <div className="ctz-route">
    <p className="ctz-journey-name">{situation.title[lang]}</p>
    <section className="ctz-block"><h3>{t("whereToGo")}</h3><p>{situation.forum[lang]}</p><Cites ids={situation.forumCites}/></section>
    <section className="ctz-block"><h3>{t("byWhen")}</h3>
      {situation.noPeriod && <div className="ctz-nodate"><strong>{t("noDateFromUs")}</strong><p>{situation.noPeriod[lang]}</p><Cites ids={situation.noPeriodCites ?? []}/></div>}
      {!!situation.rules.length && <><ul className="ctz-rules">{situation.rules.map(rule => <RuleCard key={rule.id} rule={rule} onRecord={onRecord}/>)}</ul><p className="ctz-note">{t("countingNote")}</p></>}
    </section>
    <section className="ctz-block"><h3>{t("whatItCosts")}</h3><p>{situation.cost[lang]}</p><Cites ids={situation.costCites}/></section>
    {!!situation.notes.length && <section className="ctz-block"><h3>{t("alsoKnow")}</h3><ul className="ctz-notes">{situation.notes.map(note => <li key={note.text.en}><p>{note.text[lang]}</p><Cites ids={note.cites}/></li>)}</ul></section>}
    <HumanRoute onLegalAid={onLegalAid}/>
    {backRow}
    <Disclaimer/>
  </div>;
}
