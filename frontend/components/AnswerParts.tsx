"use client";
import { ArrowUpRight, Check, ChevronDown, CircleSlash, LifeBuoy, Scale, Search, ShieldAlert, ShieldCheck, X } from "lucide-react";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { deepStageIndex, sourceHeading, sourceStanding } from "@/lib/answer-presentation";
import { safeSourceUrl } from "@/lib/source-preview";
import type { AgentCitation } from "@/lib/types";
import SourceCurrency from "./citizen/SourceCurrency";
import { useCitizenLang } from "./citizen/useCitizenLang";

const LONG_EXCERPT = 240;

export function clockLabel(seconds: number): string {
  return seconds >= 60 ? `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, "0")}s` : `${seconds}s`;
}

/** Where a source stands in the law. Read from the citation, never from prose. */
export function CurrencyBadge({ source, citizen }: { source: AgentCitation; citizen: boolean }) {
  const { t } = useCitizenLang(citizen);
  const standing = sourceStanding(source);
  return <span className={`answer-badge is-${standing.tone}`}>{t(standing.label)}</span>;
}

/** Act and section, as a reader would name the source. */
export function SourceTitle({ source, citizen }: { source: AgentCitation; citizen: boolean }) {
  const { t } = useCitizenLang(citizen);
  const { act, section, sectionIsNumber, detail } = sourceHeading(source);
  return <>
    <span className="source-title-main">{section && <b>{sectionIsNumber ? `${t("sectionLabel")} ${section}` : section}</b>}{section && <i aria-hidden="true"> · </i>}{act}</span>
    {detail && <small className="source-title-detail">{detail}</small>}
  </>;
}

export function SourcePages({ source, citizen }: { source: AgentCitation; citizen: boolean }) {
  const { t } = useCitizenLang(citizen);
  return <>{source.page_start === source.page_end ? `${t("singlePage")} ${source.page_start}` : `${t("pagesLabel")} ${source.page_start}–${source.page_end}`}</>;
}

function FastCard({ source, active, onPreview, citizen }: { source: AgentCitation; active: boolean; onPreview: () => void; citizen: boolean }) {
  const { t } = useCitizenLang(citizen);
  const [open, setOpen] = useState(false);
  const long = source.excerpt.length > LONG_EXCERPT;
  const url = safeSourceUrl(source.source_url);
  return <li className="fast-card">
    <div className="fast-card-head">
      <span className="fast-card-number" aria-hidden="true">{source.number}</span>
      <h4 className="fast-card-title"><SourceTitle source={source} citizen={citizen} /></h4>
      <CurrencyBadge source={source} citizen={citizen} />
    </div>
    <blockquote lang="en" className={long && !open ? "fast-excerpt is-collapsed" : "fast-excerpt"}>{source.excerpt}</blockquote>
    {long && <button type="button" className="fast-excerpt-toggle" aria-expanded={open} onClick={() => setOpen(value => !value)}><ChevronDown size={14} aria-hidden="true" />{open ? t("fastShowLess") : t("fastShowMore")}</button>}
    <SourceCurrency source={source} citizen={citizen} link={false} />
    <div className="fast-card-foot">
      <span><SourcePages source={source} citizen={citizen} /></span>
      <span className="fast-card-actions">
        <button type="button" className="fast-card-open" aria-expanded={active} aria-label={`${t("previewSource")} ${source.number}: ${source.title}`} onClick={onPreview}>{t("fastDetails")}</button>
        {url && <a href={url} target="_blank" rel="noreferrer">{t("fastOpenSource")}<ArrowUpRight size={14} aria-hidden="true" /></a>}
      </span>
    </div>
  </li>;
}

/**
 * A Fast result is retrieval only: nothing in it has been checked. So it is laid out
 * as what it is, a list of sources to read, and not as an answer with a preamble.
 */
export function FastBrief({ citations, lead, active, onPreview, onAskDeep, provisional = false, citizen }: { citations: AgentCitation[]; lead?: ReactNode; active: string | null; onPreview: (key: string) => void; onAskDeep?: () => void; provisional?: boolean; citizen: boolean }) {
  const { t } = useCitizenLang(citizen);
  return <div className="fast-brief">
    {provisional
      ? <p className="fast-band-note is-provisional"><Search size={15} aria-hidden="true" /> {t("provisionalNote")}</p>
      : <div className="fast-band">
          <div className="fast-band-copy">
            <p className="fast-band-title"><Search size={15} aria-hidden="true" />{t("fastKicker")}<span className="answer-badge is-warn">{t("fastUnverified")}</span></p>
            <p className="fast-band-note">{t("fastNote")}</p>
          </div>
          {onAskDeep && <div className="fast-band-action">
            <button type="button" className="fast-ask-deep" onClick={onAskDeep}><ShieldCheck size={15} aria-hidden="true" />{t("fastAskDeep")}</button>
            <small>{t("fastAskDeepHint")}</small>
          </div>}
        </div>}
    {lead}
    <h3 className="fast-list-title"><span>{t("sourcesLabel")}</span> <span className="fast-list-count">{citations.length}</span></h3>
    <ol className="fast-cards">{citations.map(source => <FastCard key={source.chunk_id} source={source} citizen={citizen} active={active === `S${source.number}`} onPreview={() => onPreview(`S${source.number}`)} />)}</ol>
  </div>;
}

/** Sits beside the answer, so a reader can hold the passage and the claim together. */
export function SourcePanel({ label, closeLabel, onClose, isDocument = false, children }: { label: string; closeLabel: string; onClose: () => void; isDocument?: boolean; children: ReactNode }) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    const keydown = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", keydown);
    return () => { document.removeEventListener("keydown", keydown); if (opener?.isConnected) opener.focus(); };
    // Only on opening: moving focus again on each render would take it from the reader.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return <section className={`source-preview ${isDocument ? "document-preview" : ""}`} aria-label={label}>
    <button ref={closeRef} className="icon-button preview-close" onClick={onClose} aria-label={closeLabel}><X size={16} /></button>
    {children}
  </section>;
}

export type DeclineKind = "insufficient" | "refusal" | "out_of_scope" | "emergency";

/** Declining is a designed outcome of this product, so it does not borrow an error's look. */
export function DeclineCard({ kind, citizen, children }: { kind: DeclineKind; citizen: boolean; children: ReactNode }) {
  const { t } = useCitizenLang(citizen);
  const Icon = kind === "emergency" ? LifeBuoy : kind === "refusal" ? Scale : kind === "out_of_scope" ? CircleSlash : ShieldAlert;
  const title = kind === "emergency" ? t("safetyLabel") : kind === "refusal" ? t("refusalLabel") : kind === "out_of_scope" ? t("declinedScopeTitle") : t("declinedEvidenceTitle");
  const why = kind === "emergency" ? t("safetyHelp") : kind === "refusal" ? t("refusalHelp") : kind === "out_of_scope" ? t("declinedScopeWhy") : t("declinedEvidenceWhy");
  return <section className="decline-card" data-kind={kind}>
    <div className="decline-head"><span className="decline-icon"><Icon size={17} strokeWidth={1.7} aria-hidden="true" /></span><h3>{title}</h3></div>
    <div className="answer-lead legal-answer" lang="en">{children}</div>
    <p className="decline-why">{why}</p>
    {kind !== "emergency" && <p className="decline-note">{t("noteCheck")}</p>}
  </section>;
}

/**
 * The wait, in the stages the job actually reports. A Fast or Auto request has no
 * stages of its own until it escalates, so it claims only the search it is doing.
 */
export function CorpusilThinking({ deep = true, stageLabel, progress, startedAt, citizen = false }: { deep?: boolean; stageLabel?: string | null; progress?: number | null; startedAt?: number; citizen?: boolean }) {
  const { t } = useCitizenLang(citizen);
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!startedAt) return;
    const tick = () => setElapsed(Math.max(0, Math.floor((Date.now() - startedAt) / 1000)));
    tick();
    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, [startedAt]);
  const current = deepStageIndex(stageLabel);
  const steps = deep ? [t("stageSearch"), t("stageRead"), t("stageCheck"), t("stageWrite")] : [t("stageSearch")];
  return <div className="stages">
    <span className="sr-only" role="status">{stageLabel || (deep ? t("deepInProgress") : t("searchInProgress"))}</span>
    <div className="stages-head" aria-hidden="true">
      <strong>{deep ? t("deepInProgress") : t("searchInProgress")}</strong>
      {!!startedAt && <span>{typeof progress === "number" && deep ? `${progress}% · ` : ""}{clockLabel(elapsed)}{deep ? ` ${t("elapsedUsual")}` : ""}</span>}
    </div>
    {deep && typeof progress === "number" && <div className="thinking-progress" role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100} aria-label={t("deepProgress")}><span style={{ width: `${Math.max(2, progress)}%` }} /></div>}
    {current < 0 && stageLabel && <p className="stages-queue" aria-hidden="true">{stageLabel}</p>}
    {!deep && elapsed >= 8 && <p className="stages-queue" role="status">{t("stageLonger")}</p>}
    <ol className="stages-list" aria-hidden="true">
      {steps.map((step, index) => {
        const state = current < 0 ? "pending" : index < current ? "done" : index === current ? "active" : "pending";
        return <li key={step} data-state={state}><span className="stages-dot">{state === "done" && <Check size={11} strokeWidth={2.6} />}</span>{step}</li>;
      })}
    </ol>
  </div>;
}
