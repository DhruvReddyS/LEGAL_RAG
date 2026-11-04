"use client";
import { CalendarPlus, CircleAlert, FileUp, RotateCcw, Sparkles } from "lucide-react";
import { useRef, useState } from "react";
import { ApiError, extractCitizenDocument } from "@/lib/api";
import { explainNotice } from "@/lib/api-citizen";
import { formatDate } from "@/lib/citizen-i18n";
import { computeDeadline } from "@/lib/citizen-law/forums";
import type { DeadlineDraft, NoticeExplanation } from "@/lib/types-citizen";
import RedactionReview from "./RedactionReview";
import { HumanRoute, NoticeCites } from "./shared";
import { useCitizenLang } from "./useCitizenLang";

const MAX_FILE_BYTES = 10 * 1024 * 1024;
const MAX_TEXT = 12000;

export default function NoticeExplainer({ onRecord, onLegalAid }: { onRecord: (draft: DeadlineDraft) => void; onLegalAid: () => void }) {
  const { lang, t } = useCitizenLang();
  const [text, setText] = useState("");
  const [stage, setStage] = useState<"input" | "review" | "working" | "result">("input");
  const [masked, setMasked] = useState("");
  const [result, setResult] = useState<NoticeExplanation | null>(null);
  const [error, setError] = useState("");
  const [reading, setReading] = useState(false);
  const [plainBusy, setPlainBusy] = useState(false);
  const [received, setReceived] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);

  const reset = () => { setText(""); setMasked(""); setResult(null); setError(""); setReceived(""); setStage("input"); };

  const explain = async (maskedText: string) => {
    setMasked(maskedText); setStage("working"); setError("");
    try { setResult(await explainNotice(maskedText, { language: lang })); setStage("result"); }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : t("somethingWrong")); setStage("review"); }
  };

  const plainWords = async () => {
    setPlainBusy(true); setError("");
    try { setResult(await explainNotice(masked, { plainLanguage: true, language: lang })); }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : t("somethingWrong")); }
    finally { setPlainBusy(false); }
  };

  const onFile = async (file: File | undefined) => {
    if (!file) return;
    if (file.size > MAX_FILE_BYTES) { setError(t("fileTooBig")); return; }
    setReading(true); setError("");
    try {
      const document = await extractCitizenDocument(file);
      setText(document.pages.map(page => page.text).join("\n\n").slice(0, MAX_TEXT));
      setStage("review");
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : t("somethingWrong")); }
    finally { setReading(false); }
  };

  if (stage === "input") return <div>
    <p className="ctz-lead">{t("noticeLead")}</p>
    <label className="ctz-field" htmlFor="ctz-notice-text"><span>{t("noticeTextLabel")}</span>
      <textarea id="ctz-notice-text" className="field ctz-textarea" rows={9} maxLength={MAX_TEXT} placeholder={t("noticePastePlaceholder")} value={text} onChange={event => setText(event.target.value)}/>
    </label>
    <div className="ctz-actions">
      <button type="button" className="button-primary ctz-primary" disabled={!text.trim()} onClick={() => setStage("review")}>{t("reviewDetails")}</button>
      <button type="button" className="ctz-btn ctz-btn-quiet" disabled={reading} onClick={() => fileInput.current?.click()}><FileUp size={15} aria-hidden="true"/>{reading ? t("reading") : t("uploadFile")}</button>
      <input ref={fileInput} className="sr-only" tabIndex={-1} aria-label={t("uploadFile")} type="file" accept="application/pdf,image/png,image/jpeg,image/webp" onChange={event => { const file = event.target.files?.[0]; event.target.value = ""; void onFile(file); }}/>
    </div>
    <p className="ctz-note">{t("uploadPrivacy")}</p>
    {error && <p className="ctz-error" role="alert">{error}</p>}
  </div>;

  if (stage === "review") return <div>
    <RedactionReview text={text} confirmLabel={t("explainThis")} onCancel={() => setStage("input")} onConfirm={value => void explain(value)}/>
    {error && <p className="ctz-error" role="alert">{error}</p>}
  </div>;

  if (stage === "working" || !result) return <p className="ctz-working" role="status">{t("explaining")}</p>;

  return <div className="ctz-result">
    <header className="ctz-result-head"><h3>{result.type_label[lang]}</h3></header>
    {result.flags.map(flag => <section key={flag.en} className="ctz-abstain" role="status"><p><CircleAlert size={15} aria-hidden="true"/> {flag[lang]}</p></section>)}

    <section className={result.abstained ? "ctz-abstain" : "ctz-block"}><h3>{result.abstained ? t("weStopHere") : t("whatThisIs")}</h3><p>{result.what_this_is[lang]}</p></section>

    <section className="ctz-block"><h3>{t("whatItDemands")}</h3>
      {result.demands.length ? <ul className="ctz-quotes">{result.demands.map(item => <li key={item}><blockquote>{item}</blockquote></li>)}</ul> : <p className="ctz-note">{t("noDemands")}</p>}
    </section>

    <section className="ctz-block"><h3>{t("theDeadline")}</h3>
      {result.statutory_deadline && <div className="ctz-nodate"><strong>{t("lawSays")}</strong><p>{result.statutory_deadline[lang]}</p></div>}
      <strong className="ctz-sub">{t("noticeSays")}</strong>
      {result.deadlines.length ? <>
        <label className="ctz-field" htmlFor="ctz-received"><span>{t("receivedOn")}</span><input id="ctz-received" className="field" type="date" value={received} onChange={event => setReceived(event.target.value)}/></label>
        <ul className="ctz-quotes">{result.deadlines.map(item => {
          const due = received ? computeDeadline({ add: { days: item.days } }, received) : null;
          return <li key={`${item.days}-${item.quote}`}><blockquote>{item.quote}</blockquote>
            {due && <div className="ctz-due" role="status"><span>{t("dueIf")}</span><strong>{formatDate(due, lang)}</strong><p className="ctz-note">{t("checkFromDate")}</p>
              <button type="button" className="ctz-link" onClick={() => onRecord({ title: result.type_label.en, due_on: due, source: "notice", provision_label: result.provisions[0]?.label ?? null })}><CalendarPlus size={14} aria-hidden="true"/>{t("addToMatter")}</button></div>}
          </li>;
        })}</ul>
      </> : <p className="ctz-note">{t("noDeadlineFound")}</p>}
      {!!result.dates.length && <><strong className="ctz-sub">{t("datesInIt")}</strong><ul className="ctz-facts">{result.dates.map(item => <li key={item.raw}><strong>{item.raw}</strong><span>{item.context}</span>
        {item.iso && <button type="button" className="ctz-link" onClick={() => onRecord({ title: result.type_label.en, due_on: item.iso!, source: "notice", provision_label: result.provisions[0]?.label ?? null })}><CalendarPlus size={14} aria-hidden="true"/>{t("addToMatter")}</button>}</li>)}</ul></>}
      {!!result.amounts.length && <><strong className="ctz-sub">{t("amountsInIt")}</strong><p>{result.amounts.join(" · ")}</p></>}
    </section>

    <section className={result.abstained ? "ctz-abstain" : "ctz-block"}><h3>{t("theRisk")}</h3><p>{result.risk[lang]}</p><NoticeCites items={result.provisions}/></section>

    {!!result.cited_provisions.length && <section className="ctz-block"><h3>{t("sectionsItCites")}</h3><ul className="ctz-facts">{result.cited_provisions.map(item => <li key={`${item.code}-${item.section}`}>
      <strong lang="en">{item.raw}</strong>
      {item.status === "replaced" ? <span className="ctz-repealed">{t("replacedLabel")} {item.replaced_on ? formatDate(item.replaced_on, lang) : ""}.{item.successors.length ? <>{t("nowIs")} <b lang="en">{item.successors.join(", ")}</b></> : item.no_successor ? t("noSuccessor") : t("noMappingKnown")}{item.ingredients_changed ? ` · ${t("elementsChanged")}` : ""}</span> : item.status === "not_checked" ? <span>{t("notChecked")}</span> : null}
    </li>)}</ul></section>}

    <section className="ctz-block ctz-plain"><h3><Sparkles size={15} aria-hidden="true"/>{t("plainWords")}</h3>
      {result.plain ? <><p className="ctz-note">{t("plainLabel")}</p><p lang={result.plain.language}>{result.plain.summary}</p>{!!result.plain.demands.length && <ul className="ctz-quotes">{result.plain.demands.map(item => <li key={item.quote}><p lang={result.plain!.language}>{item.plain}</p><blockquote>{item.quote}</blockquote></li>)}</ul>}</> : <>
        <p className="ctz-note">{t("plainWordsHint")}</p>
        {result.plain_status === "unavailable" && <p className="ctz-note" role="status">{t("plainUnavailable")}</p>}
        {result.plain_status === "rejected" && <p className="ctz-note" role="status">{t("plainRejected")}</p>}
        <button type="button" className="ctz-btn ctz-btn-quiet" disabled={plainBusy} onClick={() => void plainWords()}>{plainBusy ? t("plainWorking") : t("plainWords")}</button>
      </>}
    </section>
    {error && <p className="ctz-error" role="alert">{error}</p>}

    <HumanRoute onLegalAid={onLegalAid}/>
    <p className="ctz-disclaimer">{result.disclaimer[lang]}</p>
    <div className="ctz-actions"><button type="button" className="ctz-link" onClick={reset}><RotateCcw size={14} aria-hidden="true"/>{t("explainAnother")}</button></div>
  </div>;
}
