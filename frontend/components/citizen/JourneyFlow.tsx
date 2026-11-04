"use client";
import { ArrowLeft, ArrowRight, Siren } from "lucide-react";
import { useState } from "react";
import { findStep, JOURNEYS, type Journey, type ToolLink } from "@/lib/citizen-law/journeys";
import { AskQuestion, Cites, Disclaimer, HumanRoute } from "./shared";
import { useCitizenLang } from "./useCitizenLang";

export default function JourneyFlow({ initialJourney, onAsk, onTool }: { initialJourney?: string; onAsk?: (question: string) => void; onTool: (link: ToolLink) => void }) {
  const { lang, t } = useCitizenLang();
  const [journey, setJourney] = useState<Journey | null>(JOURNEYS.find(item => item.id === initialJourney) ?? null);
  const [path, setPath] = useState<string[]>(journey ? [journey.start] : []);
  const open = (next: Journey) => { setJourney(next); setPath([next.start]); };
  if (!journey) {
    return <div>
      <p className="ctz-lead">{t("journeysLead")}</p>
      <ul className="ctz-choice-list">{JOURNEYS.map(item => <li key={item.id}><button type="button" onClick={() => open(item)}><span><strong>{item.title[lang]}</strong><small>{item.blurb[lang]}</small></span><ArrowRight size={16} aria-hidden="true"/></button></li>)}</ul>
      <Disclaimer/>
    </div>;
  }
  const step = findStep(journey, path[path.length - 1]);
  if (!step) return null;
  const isEnd = !step.options?.length;
  return <div className="ctz-journey">
    <p className="ctz-journey-name">{journey.title[lang]}</p>
    <nav className="ctz-progress" aria-label={journey.title[lang]}>{path.map((id, index) => <span key={`${id}-${index}`} aria-current={index === path.length - 1 ? "step" : undefined}/>)}</nav>
    <section className={`ctz-step ${step.emergency ? "is-urgent" : ""}`} aria-live="polite">
      {step.emergency && <Siren size={20} aria-hidden="true" className="ctz-step-icon"/>}
      <h3>{step.title[lang]}</h3>
      {step.body && <p>{step.body[lang]}</p>}
      {step.cites && <Cites ids={step.cites}/>}
      {step.options && <div className="ctz-options">{step.options.map(option => <button type="button" key={option.next} className="ctz-option" onClick={() => setPath(current => [...current, option.next])}>{option.label[lang]}<ArrowRight size={15} aria-hidden="true"/></button>)}</div>}
      {step.tools && <div className="ctz-actions">{step.tools.map(tool => <button type="button" key={tool.label.en} className="ctz-btn ctz-btn-quiet" onClick={() => onTool(tool.to)}>{tool.label[lang]}<ArrowRight size={15} aria-hidden="true"/></button>)}</div>}
    </section>
    {step.ask && <AskQuestion question={step.ask[lang]} onAsk={onAsk}/>}
    {isEnd && <HumanRoute onLegalAid={() => onTool({ tool: "legal-aid" })}/>}
    <div className="ctz-actions ctz-step-nav">
      {path.length > 1 ? <button type="button" className="ctz-link" onClick={() => setPath(current => current.slice(0, -1))}><ArrowLeft size={14} aria-hidden="true"/>{t("stepBack")}</button> : <button type="button" className="ctz-link" onClick={() => { setJourney(null); setPath([]); }}><ArrowLeft size={14} aria-hidden="true"/>{t("toolJourneys")}</button>}
      {path.length > 1 && <button type="button" className="ctz-link" onClick={() => setPath([journey.start])}>{t("startOver")}</button>}
    </div>
    <Disclaimer/>
  </div>;
}
