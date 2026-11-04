"use client";
import { ArrowUpRight, Languages, LifeBuoy, MessageSquareText, Phone } from "lucide-react";
import { LANG_LABELS, setLang } from "@/lib/citizen-i18n";
import { LANGS, provision, type Provision } from "@/lib/citizen-law/law";
import type { NoticeProvision } from "@/lib/types-citizen";
import { useCitizenLang } from "./useCitizenLang";

export function LangSwitcher() {
  const { lang, t } = useCitizenLang();
  return <div className="ctz-lang" role="group" aria-label={t("language")}>
    <Languages size={15} aria-hidden="true"/>
    {LANGS.map(code => <button key={code} type="button" lang={code} aria-pressed={lang === code} onClick={() => setLang(code)}>{LANG_LABELS[code]}</button>)}
  </div>;
}

type CiteCard = Pick<Provision, "label" | "actName" | "quote" | "page" | "sourceUrl">;

function CiteDetails({ card }: { card: CiteCard }) {
  const { t } = useCitizenLang();
  return <details className="ctz-cite">
    <summary>{card.label}</summary>
    <div className="ctz-cite-body">
      <p className="ctz-cite-act" lang="en">{card.actName}</p>
      <blockquote lang="en">“{card.quote}”</blockquote>
      <p className="ctz-cite-meta"><span>{t("inOriginal")}{card.page ? ` · ${t("page")} ${card.page}` : ""}</span>{card.sourceUrl && <a href={card.sourceUrl} target="_blank" rel="noreferrer">{t("openOfficial")}<ArrowUpRight size={13} aria-hidden="true"/></a>}</p>
    </div>
  </details>;
}

/** Every legal statement in these tools carries one of these. */
export function Cites({ ids }: { ids: string[] }) {
  if (!ids.length) return null;
  return <div className="ctz-cites">{ids.map(id => <CiteDetails key={id} card={provision(id)}/>)}</div>;
}

export function NoticeCites({ items }: { items: NoticeProvision[] }) {
  if (!items.length) return null;
  return <div className="ctz-cites">{items.map(item => <CiteDetails key={item.id} card={{ label: item.label, actName: item.act_name, quote: item.quote, page: item.page, sourceUrl: item.source_url ?? "" }}/>)}</div>;
}

export function HumanRoute({ onLegalAid, children }: { onLegalAid?: () => void; children?: React.ReactNode }) {
  const { t } = useCitizenLang();
  return <aside className="ctz-human">
    <LifeBuoy size={18} aria-hidden="true"/>
    <div>
      <strong>{t("talkToPerson")}</strong>
      {children && <p>{children}</p>}
      <div className="ctz-actions">
        <a className="ctz-btn" href="tel:15100"><Phone size={15} aria-hidden="true"/>{t("call15100")}</a>
        {onLegalAid && <button type="button" className="ctz-btn ctz-btn-quiet" onClick={onLegalAid}>{t("checkLegalAid")}</button>}
      </div>
    </div>
  </aside>;
}

export function AskQuestion({ question, onAsk }: { question: string; onAsk?: (question: string) => void }) {
  const { t } = useCitizenLang();
  return <div className="ctz-ask">
    <span>{t("goodQuestion")}</span>
    <p>{question}</p>
    {onAsk && <button type="button" className="ctz-btn" onClick={() => onAsk(question)}><MessageSquareText size={15} aria-hidden="true"/>{t("askThis")}</button>}
  </div>;
}

export function Disclaimer() {
  const { t } = useCitizenLang();
  return <p className="ctz-disclaimer">{t("informationNotAdvice")}</p>;
}

export function downloadText(filename: string, content: string, type = "text/plain;charset=utf-8") {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
