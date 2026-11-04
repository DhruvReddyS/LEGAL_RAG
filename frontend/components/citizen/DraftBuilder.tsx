"use client";
import { ArrowLeft, ArrowRight, Check, Copy, Download, Printer } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { DRAFT_TEMPLATES, renderDraft, repealWarnings, type DraftTemplate } from "@/lib/citizen-law/drafts";
import { Cites, Disclaimer, downloadText } from "./shared";
import { useCitizenLang } from "./useCitizenLang";

export default function DraftBuilder({ initialTemplate }: { initialTemplate?: string }) {
  const { lang, t } = useCitizenLang();
  const [template, setTemplate] = useState<DraftTemplate | null>(DRAFT_TEMPLATES.find(item => item.id === initialTemplate) ?? null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [copied, setCopied] = useState(false);
  useEffect(() => { const next = DRAFT_TEMPLATES.find(item => item.id === initialTemplate); if (next) { setTemplate(next); setValues({}); } }, [initialTemplate]);
  const rendered = useMemo(() => template ? renderDraft(template, values) : null, [template, values]);
  const warnings = useMemo(() => repealWarnings(Object.values(values).join(" ")), [values]);

  if (!template || !rendered) return <div>
    <p className="ctz-lead">{t("draftLead")}</p>
    <h3 className="ctz-section-title">{t("draftPick")}</h3>
    <ul className="ctz-choice-list">{DRAFT_TEMPLATES.map(item => <li key={item.id}><button type="button" onClick={() => { setTemplate(item); setValues({}); }}><span><strong>{item.title[lang]}</strong><small>{item.blurb[lang]}</small></span><ArrowRight size={16} aria-hidden="true"/></button></li>)}</ul>
    <Disclaimer/>
  </div>;

  const copy = async () => { try { await navigator.clipboard.writeText(rendered.text); setCopied(true); window.setTimeout(() => setCopied(false), 1800); } catch { setCopied(false); } };

  return <div className="ctz-draft">
    <div className="ctz-no-print">
      <p className="ctz-journey-name">{template.title[lang]}</p>
      <p className="ctz-note">{template.guidance[lang]}</p>
      <Cites ids={template.cites}/>
      <form className="ctz-form" onSubmit={event => event.preventDefault()}>
        {template.fields.map(field => <label key={field.id} className="ctz-field" htmlFor={`draft-${field.id}`}><span>{field.label[lang]}</span>
          {field.multiline ? <textarea id={`draft-${field.id}`} className="field ctz-textarea" rows={3} value={values[field.id] ?? ""} onChange={event => setValues(current => ({ ...current, [field.id]: event.target.value }))}/> : <input id={`draft-${field.id}`} className="field" value={values[field.id] ?? ""} onChange={event => setValues(current => ({ ...current, [field.id]: event.target.value }))}/>}
        </label>)}
      </form>
      {warnings.map(item => <div key={item.cite} className="ctz-abstain" role="status"><p>{item.warning[lang]}</p><Cites ids={[item.cite]}/></div>)}
      <p className="ctz-note" role="status">{rendered.complete ? t("allFilled") : `${t("blanksLeft")}: ${rendered.blanks.map(id => template.fields.find(field => field.id === id)?.label[lang] ?? id).join(", ")}`}</p>
    </div>
    <section className="ctz-block"><h3 className="ctz-no-print">{t("draftPreview")}</h3>
      <pre className="ctz-draft-text" lang="en" tabIndex={0}>{rendered.text}</pre>
      <div className="ctz-actions ctz-no-print">
        <button type="button" className="ctz-btn" onClick={() => void copy()}>{copied ? <Check size={15} aria-hidden="true"/> : <Copy size={15} aria-hidden="true"/>}{copied ? t("copied") : t("copy")}</button>
        <button type="button" className="ctz-btn ctz-btn-quiet" onClick={() => downloadText(`draft-${template.id}.txt`, rendered.text)}><Download size={15} aria-hidden="true"/>{t("download")}</button>
        <button type="button" className="ctz-btn ctz-btn-quiet" onClick={() => window.print()}><Printer size={15} aria-hidden="true"/>{t("print")}</button>
      </div>
      <p className="ctz-note ctz-no-print">{t("draftEnglishNote")} {t("draftNotFiled")}</p>
    </section>
    <div className="ctz-actions ctz-step-nav ctz-no-print"><button type="button" className="ctz-link" onClick={() => setTemplate(null)}><ArrowLeft size={14} aria-hidden="true"/>{t("draftPick")}</button></div>
    <div className="ctz-no-print"><Disclaimer/></div>
  </div>;
}
