"use client";
import FollowUps from "@/components/FollowUps";
import { Check, Clock3, Copy, Pencil, RotateCcw, ShieldCheck, ThumbsDown, ThumbsUp, Volume2, Square } from "lucide-react";
import { Fragment, ReactNode, useEffect, useRef, useState } from "react";
import HumanHelp from "@/components/platform/HumanHelp";
import { AnswerExportMenu, PrintOnlySources } from "@/components/platform/AnswerTools";
import ReactMarkdown from "react-markdown";
import { isFastBrief, NO_LEAD, presentAnswer, sourceHeading } from "@/lib/answer-presentation";
import { CorpusilThinking, CurrencyBadge, DeclineCard, type DeclineKind, FastBrief, SourcePages, SourcePanel, SourceTitle } from "./AnswerParts";
import { isOutOfScope, safetyKind, shouldOfferHuman } from "@/lib/citizen-chat";
import { HumanRoute } from "./citizen/shared";
import SourceCurrency from "./citizen/SourceCurrency";
import TranslatedAnswer from "./citizen/TranslatedAnswer";
import { useCitizenLang } from "./citizen/useCitizenLang";
import { submitFeedback } from "@/lib/api";
import type { ChatMessage } from "@/lib/types";

type TimingRow = { label: string; ms: number; detail?: boolean };

const stageLabels: Record<string, string> = {
  role_context: "Role and route setup",
  query_understanding: "Query understanding",
  retrieval: "Retrieval",
  reasoning: "Answer reasoning",
  verification: "Claim verification",
  retry: "Retry preparation",
  response_generation: "Response formatting",
};

function numeric(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function retrievalDetails(value: unknown, prefix: string): TimingRow[] {
  if (!value || typeof value !== "object") return [];
  const record = value as Record<string, unknown>;
  return [
    ["Embedding", record.embedding_ms],
    ["Vector / lexical search", record.qdrant_ms],
    ["Cross-encoder reranking", record.reranking_ms],
  ].flatMap(([label, raw]) => {
    const ms = numeric(raw);
    return ms === null ? [] : [{ label: `${prefix} · ${label}`, ms, detail: true }];
  });
}

function llmDetails(calls: Array<Record<string, unknown>>, prefix: string): TimingRow[] {
  return calls.flatMap((call, index) => {
    const callPrefix = calls.length > 1 ? `${prefix} · call ${index + 1}` : prefix;
    return [
      ["Model load", call.ollama_load_duration_ms],
      ["Prompt evaluation", call.ollama_prompt_eval_duration_ms],
      ["Token generation", call.ollama_eval_duration_ms],
    ].flatMap(([label, raw]) => {
      const ms = numeric(raw);
      return ms === null ? [] : [{ label: `${callPrefix} · ${label}`, ms, detail: true }];
    });
  });
}

function timingRows(message: ChatMessage): TimingRow[] {
  const timings = message.timingsMs ?? {};
  const metrics = message.pipelineMetrics ?? [];
  const rows: TimingRow[] = [];
  if (metrics.length) {
    for (const metric of metrics) {
      if (metric.stage === "workflow_total") continue;
      rows.push({
        label: `${stageLabels[metric.stage] ?? metric.stage}${metric.retry_index ? ` · retry ${metric.retry_index}` : ""}`,
        ms: metric.duration_ms,
      });
      if (metric.stage === "retrieval") {
        const suffix = String(metric.retry_index || 0);
        const initial = timings[`retrieval_${suffix}_initial`];
        rows.push(...retrievalDetails(initial, initial ? "Initial pass" : "Search pass"));
        rows.push(...retrievalDetails(timings[`retrieval_${suffix}`], initial ? "Fallback pass" : "Search pass"));
      }
      rows.push(...llmDetails(metric.llm_calls, stageLabels[metric.stage] ?? metric.stage));
    }
  } else {
    const retrieval = numeric(timings.retrieval_total_ms);
    if (retrieval !== null) {
      rows.push({ label: "Retrieval", ms: retrieval });
      for (const [label, key] of [["Embedding", "embedding_ms"], ["Vector / lexical search", "qdrant_ms"], ["Cross-encoder reranking", "reranking_ms"]] as const) {
        const ms = numeric(timings[key]);
        if (ms !== null) rows.push({ label: `Search pass · ${label}`, ms, detail: true });
      }
      const workflow = numeric(timings.workflow_total_ms);
      if (workflow !== null && workflow > retrieval) rows.push({ label: "Filtering and response assembly", ms: workflow - retrieval });
    }
  }
  const workflow = numeric(timings.workflow_total_ms);
  const api = numeric(timings.api_total_ms);
  const serverTotal = api ?? workflow;
  if (api !== null && workflow !== null && api > workflow) rows.push({ label: "API, database and server overhead", ms: api - workflow });
  if (message.clientElapsedMs !== undefined && serverTotal !== null && message.clientElapsedMs > serverTotal) {
    rows.push({ label: "Network, browser and queue wait", ms: message.clientElapsedMs - serverTotal });
  }
  const total = message.clientElapsedMs ?? api ?? workflow;
  if (total !== null) rows.push({ label: "End-to-end total", ms: total });
  return rows.filter(row => row.ms >= 0);
}

function durationLabel(ms: number): string {
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(ms < 10_000 ? 2 : 1)} s`;
}

function llmWallTime(message: ChatMessage): number | null {
  const calls = (message.pipelineMetrics ?? []).flatMap(metric => metric.llm_calls ?? []);
  if (!calls.length) return null;
  const measured = calls.map(call => numeric(call.wall_ms)).filter((value): value is number => value !== null);
  return measured.length ? measured.reduce((total, value) => total + value, 0) : null;
}

export default function MessageBubble({ message, onRegenerate, onForgetDocuments, onEdit, role, question, citizen = false, onLegalAid, onAskDeep }: { message: ChatMessage; onRegenerate?: () => void; onForgetDocuments?: () => void; onEdit?: (text: string) => void; role?: string; question?: string; citizen?: boolean; onLegalAid?: () => void; onAskDeep?: () => void }) {
  const articleRef = useRef<HTMLElement>(null);
  const { t: text } = useCitizenLang(citizen);
  const safety = safetyKind(message);
  const outOfScope = isOutOfScope(message);
  if (message.documents?.some(document => !document.pages.length)) onRegenerate = undefined;
  const [active, setActive] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);
  const [feedbackError, setFeedbackError] = useState(false);
  // The buttons previously set local state and sent nothing. Toggling off
  // is not "no opinion" - the API has no delete - so a second press on the
  // same verdict is a no-op rather than a silent local reset.
  const rate = async (rating: "up" | "down") => {
    if (!message.messageId || feedback === rating) return;
    const previous = feedback;
    setFeedback(rating);
    setFeedbackError(false);
    try {
      await submitFeedback(message.messageId, rating);
    } catch {
      setFeedback(previous);
      setFeedbackError(true);
    }
  };
  const [feedback, setFeedback] = useState<"up" | "down" | null>(null);
  const [speaking, setSpeaking] = useState(false);
  const [canSpeak, setCanSpeak] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editedText, setEditedText] = useState(message.content);
  useEffect(() => { setCanSpeak("speechSynthesis" in window); return () => { if ("speechSynthesis" in window) window.speechSynthesis.cancel(); }; }, []);
  // A reopened chat keeps no lane, so its opening sentence is what marks a Fast result.
  const fastMode = message.responseMode === "fast" || (message.responseMode === undefined && isFastBrief(message.content));
  const presentation = presentAnswer(message.content, {
    fast: fastMode,
    evidenceStrength: message.evidenceStrength ?? null,
  });
  const citations = message.citations ?? [];
  const declined: DeclineKind | null = safety === "emergency" ? "emergency" : safety === "refusal" ? "refusal" : outOfScope ? "out_of_scope" : presentation.abstained ? "insufficient" : null;
  const fastList = fastMode && !declined && citations.length > 0;
  // A Deep answer that passed, or a reopened one whose every source the verifier marked.
  const verifiedGrade = !fastMode && !declined && citations.length > 0 && (message.responseMode === "deep"
    ? message.evidenceStrength === "strong" || message.evidenceStrength === "moderate"
    : citations.every(item => item.verification_status === "verified"));
  const source = citations.find(item => active === `S${item.number}`);
  const document = message.documents?.find((_, index) => active === `D${index + 1}`);
  const elapsed = message.clientElapsedMs ?? (typeof message.timingsMs?.api_total_ms === "number" ? message.timingsMs.api_total_ms : null);
  const elapsedLabel = elapsed === null ? null : elapsed < 1000 ? `${Math.round(elapsed)} ms` : `${(elapsed / 1000).toFixed(elapsed < 10_000 ? 1 : 0)} s`;
  const llmElapsed = llmWallTime(message);
  const llmElapsedLabel = llmElapsed === null ? null : durationLabel(llmElapsed);
  const performanceRows = timingRows(message);
  const bottleneck = performanceRows.filter(row => !row.detail && row.label !== "End-to-end total").sort((a, b) => b.ms - a.ms)[0];
  const toggle = (key: string) => setActive(current => current === key ? null : key);
  const inline = (children: ReactNode): ReactNode => Array.isArray(children) ? children.map((child, index) => <Fragment key={index}>{inline(child)}</Fragment>) : typeof children === "string" ? children.split(/(\[Source \d+\])/g).map((part, index) => {
    const number = part.match(/^\[Source (\d+)\]$/)?.[1];
    return number && citations.some(item => item.number === Number(number)) ? <button key={index} className="source-chip inline-source" aria-label={`${text("previewSource")} ${number}`} aria-expanded={active === `S${number}`} onClick={() => toggle(`S${number}`)}>{number}</button> : part;
  }) : children;
  const panel = (source || document) && <SourcePanel label={text("sourcePreviewLabel")} closeLabel={text("closePreview")} onClose={() => setActive(null)} isDocument={!!document}>{source ? <>
    <div className="source-eyebrow"><strong>{text("corpusSource")} {source.number}</strong><CurrencyBadge source={source} citizen={citizen} />{source.verification_status === "verified" ? <span className="answer-badge is-ok">{text("sourceChecked")}</span> : source.verification_status === "partial" ? <span className="answer-badge is-warn">{text("sourcePartial")}</span> : <span className="answer-badge is-warn">{text("fastUnverified")}</span>}</div>
    <h3><SourceTitle source={source} citizen={citizen} /></h3>
    <p className="source-pages"><SourcePages source={source} citizen={citizen} /></p>
    <SourceCurrency source={source} citizen={citizen}/>
    <blockquote lang="en">{source.excerpt}</blockquote>
  </> : document && <><small>{text("yourDocument")}</small><h3>{document.filename}</h3><p className="source-pages">{text("documentContext")}</p>{document.pages.length ? document.pages.map(page => <div key={page.page}><small>{text("page")} {page.page}</small><blockquote>{page.text}</blockquote></div>) : <p>{text("documentGone")}</p>}{onForgetDocuments && <button className="answer-text-action" onClick={() => { onForgetDocuments(); setActive(null); }}>{text("forgetDocument")}</button>}</>}</SourcePanel>;
  const markdown = (text: string) => <ReactMarkdown components={{ p: ({ children }) => <p>{inline(children)}</p>, li: ({ children }) => <li>{inline(children)}</li>, strong: ({ children }) => <strong>{inline(children)}</strong> }}>{text}</ReactMarkdown>;
  const speak = () => {
    window.speechSynthesis.cancel();
    if (speaking) { setSpeaking(false); return; }
    const spoken = fastList ? citations.map(item => `${sourceHeading(item).act}. ${item.excerpt}`).join(" ") : presentation.explanation;
    const utterance = new SpeechSynthesisUtterance(spoken.replace(/\[Source \d+\]|[*#_]/g, ""));
    utterance.lang = "en-IN"; utterance.onend = utterance.onerror = () => setSpeaking(false);
    setSpeaking(true); window.speechSynthesis.speak(utterance);
  };
  if (message.loading) {
    const thinking = <CorpusilThinking deep={(message.responseMode ?? message.requestedMode) === "deep"} stageLabel={message.stageLabel} progress={message.jobProgress} startedAt={message.timestamp} citizen={citizen} />;
    // A Fast brief exists whenever a low-confidence result escalated. Showing
    // it costs nothing - it was already computed - and replaces a blank
    // multi-minute wait with something the reader can start on.
    if (!message.provisional) return thinking;
    return <div className="provisional-turn">
      {thinking}
      <section className="provisional-brief" aria-label={text("provisionalLabel")}>
        <FastBrief citations={citations} provisional active={active} onPreview={toggle} citizen={citizen} />
      </section>
      {panel}
    </div>;
  }
  if (message.role === "user") return <div className={`user-turn ${editing ? "is-editing" : ""}`}><article className="user-message">{editing ? <><textarea autoFocus aria-label={text("editYourQuestion")} value={editedText} maxLength={4000} rows={3} onChange={event => setEditedText(event.target.value)} onKeyDown={event => { if (event.key === "Escape") setEditing(false); if ((event.metaKey || event.ctrlKey) && event.key === "Enter" && editedText.trim()) { setEditing(false); onEdit?.(editedText.trim()); } }}/><p className="edit-hint">{text("editHint")}</p><div className="edit-actions"><button onClick={() => setEditing(false)}>{text("cancel")}</button><button disabled={!editedText.trim()} onClick={() => { setEditing(false); onEdit?.(editedText.trim()); }}>{text("saveResend")}</button></div></> : <p>{message.content}</p>}{message.documents?.map((doc, index) => <span className="document-chip" key={doc.id}>D{index + 1} · {doc.filename}</span>)}</article>{!editing && <div className="user-actions"><button className="answer-action" aria-label={text("copyQuestion")} onClick={async () => { try { await navigator.clipboard.writeText(message.content); setCopied(true); } catch { setCopyError(true); } }}>{copied ? <Check size={14}/> : <Copy size={14}/>}</button>{onEdit && <button className="answer-action" aria-label={text("editQuestion")} onClick={() => { setEditedText(message.content); setEditing(true); }}><Pencil size={14}/></button>}</div>}{copyError && <p className="edit-hint">{text("clipboardQuestion")}</p>}</div>;
  if (message.stopped) return <div className="stopped-answer"><span>{message.content}</span>{onRegenerate && <button onClick={onRegenerate}><RotateCcw size={13}/>{text("tryAgain")}</button>}</div>;
  if (message.error) return <article className="answer-error" role="alert">{message.error}{onRegenerate && <button onClick={onRegenerate}>{text("tryAgain")}</button>}</article>;
  return <article className="assistant-message" ref={articleRef}>
    <div className="answer-byline"><span className="corpus-signature">Corpusil</span><span>{message.category || "Legal research"}</span></div>
    {citizen && message.messageId && citations.length > 0 && <TranslatedAnswer messageId={message.messageId} render={markdown} />}
    {fastList ? <FastBrief citations={citations} active={active} onPreview={toggle} onAskDeep={onAskDeep} citizen={citizen} lead={!isFastBrief(message.content) && <div className="answer-lead legal-answer" lang="en">{markdown(presentation.explanation)}</div>} /> : <>
    {verifiedGrade && <div className="answer-verdict" data-grade={message.evidenceStrength === "moderate" ? "moderate" : "strong"}><ShieldCheck size={18} aria-hidden="true" /><div><strong>{text("verifiedTitle")}</strong><span>{text("verifiedDetail")}</span></div>{message.evidenceStrength && <details className="confidence-help"><summary className="confidence-pill">{message.evidenceStrength === "strong" ? text("gradeStrong") : text("gradeModerate")}</summary><p>{text("gradeHelp")}</p></details>}</div>}
    {declined
      ? <DeclineCard kind={declined} citizen={citizen}>{!(safety && presentation.explanation === NO_LEAD) && markdown(presentation.explanation)}</DeclineCard>
      : <div className="answer-lead legal-answer" lang="en">{markdown(presentation.explanation)}</div>}
    <div className="trust-row" aria-label={text("evidenceAndSources")}>
      {!verifiedGrade && !declined && <details className="confidence-help"><summary className="confidence-pill">{message.evidenceStrength === "strong" ? text("gradeStrong") : message.evidenceStrength === "moderate" ? text("gradeModerate") : text("gradeNotKept")}</summary><p>{text("gradeHelp")}</p></details>}
      {citations.length > 0 && <span className="source-label">{text("sourcesLabel")}</span>}{citations.map(item => { const heading = sourceHeading(item); return <button key={item.chunk_id} className="source-chip source-pill" onClick={() => toggle(`S${item.number}`)} aria-expanded={active === `S${item.number}`} aria-label={`${text("previewSource")} ${item.number}: ${item.title}`}><b>{item.number}</b><span>{heading.section ? `${heading.sectionIsNumber ? "s." : ""}${heading.section}, ` : ""}{heading.act}</span></button>; })}
      {!citations.length && !declined && <span>{text("noCitedAuthority")}</span>}
      {message.documents?.map((doc, index) => <button key={doc.id} className="document-chip" onClick={() => toggle(`D${index + 1}`)} aria-expanded={active === `D${index + 1}`} title={`Your document: ${doc.filename}`}>D{index + 1}</button>)}
    </div>
    </>}
    {!!message.sectionConfidence?.length && (
      <details className="section-grading">
        <summary>
          {text("groundingTitle")}
          {message.sectionConfidence.some(row => row.confidence === "limited") && (
            <span className="grading-flag"> · {text("groundingFlag")}</span>
          )}
        </summary>
        <ul>
          {message.sectionConfidence.map(row => (
            <li key={row.section} data-confidence={row.confidence}>
              <span className="grading-section">{row.section}</span>
              <span className={`grading-label grading-${row.confidence}`}>{row.confidence}</span>
              <span className="grading-reason">{row.reason}</span>
            </li>
          ))}
        </ul>
        <p className="grading-note">
          {text("groundingNote")}
        </p>
      </details>
    )}
    {panel}
    <div className="legal-answer answer-body" lang="en">{presentation.basis && <><h3 lang={undefined}>{text("legalBasis")}</h3>{markdown(presentation.basis)}</>}{!fastList && markdown(presentation.other)}{presentation.limits && <details open className="answer-limits"><summary>{text("limitsTitle")}</summary>{markdown(presentation.limits)}</details>}</div>
    {presentation.footer && <section className="source-currency" aria-label="Source currency"><h3>{text("stillLaw")}</h3>{markdown(presentation.footer)}</section>}
    {presentation.abstained && !outOfScope && !(citizen && !safety) && <HumanHelp role={role} />}
    {citizen && !safety && !outOfScope && shouldOfferHuman(message) && <div className="ctz-chat-human"><HumanRoute onLegalAid={onLegalAid}>{text("humanNudge")}</HumanRoute></div>}
    {!(declined && !citations.length) && <aside className="legal-note" aria-label={text("noteLabel")}><ShieldCheck size={17}/><div><strong>{text("beforeRely")}</strong><p>{citations.some(item => item.repeal_label === "no_longer_in_force") ? text("noteRepealed") : citations.some(item => item.repeal_label === "concerns_repealed_provision") ? text("noteMoved") : citations.length && citations.every(item => item.current_status === "current") ? text("noteCurrent") : text("noteUnknown")} {text("noteCheck")}</p></div></aside>}
    <PrintOnlySources message={message} question={question} />
    <div className="answer-actions" aria-label={text("answerActions")}><AnswerExportMenu message={message} question={question} articleRef={articleRef} citizen={citizen} /><button className="answer-action" aria-label={copied ? text("answerCopied") : text("copyAnswer")} onClick={async () => { try { await navigator.clipboard.writeText(message.content); setCopied(true); setCopyError(false); } catch { setCopyError(true); } }}>{copied ? <Check size={16}/> : <Copy size={16}/>}</button><button className="answer-action" aria-label={text("markHelpful")} aria-pressed={feedback === "up"} disabled={!message.messageId} onClick={() => rate("up")}><ThumbsUp size={16}/></button><button className="answer-action" aria-label={text("markNotHelpful")} aria-pressed={feedback === "down"} disabled={!message.messageId} onClick={() => rate("down")}><ThumbsDown size={16}/></button>{onRegenerate && <button className="answer-action" aria-label={text("regenerate")} onClick={onRegenerate}><RotateCcw size={16}/></button>}<span className="performance-pills">{llmElapsedLabel && <span className="answer-performance" title="Measured wall time spent in Ollama calls across this answer." aria-label={`LLM time ${llmElapsedLabel}`}><span>LLM</span>{llmElapsedLabel}</span>}{elapsedLabel && <span className="answer-performance" title="Time from sending your question to receiving the finished response in this tab, including network and review wait." aria-label={`Total response time ${elapsedLabel}`}><Clock3 size={13}/><span>Total</span>{elapsedLabel}</span>}</span>{canSpeak && <button className="listen-button" onClick={speak} aria-pressed={speaking}>{speaking ? <Square size={14}/> : <Volume2 size={16}/>} {speaking ? text("stopReading") : text("listen")}</button>}</div>
    {performanceRows.length > 0 && <details className="rag-timing"><summary><span><Clock3 size={13}/>RAG timing</span>{bottleneck && <small>Slowest: {bottleneck.label} · {durationLabel(bottleneck.ms)}</small>}</summary><div className="rag-timing-list">{performanceRows.map((row, index) => <div key={`${row.label}-${index}`} className={row.detail ? "is-detail" : row.label === "End-to-end total" ? "is-total" : ""}><span>{row.label}</span><b>{durationLabel(row.ms)}</b></div>)}</div></details>}
    {onRegenerate && !safety && !outOfScope && !presentation.abstained && !message.stopped && role !== "admin" && <FollowUps citations={citations} role={role} citizen={citizen} />}
    {copyError && <p role="status" className="answer-footer">{text("clipboardAnswer")}</p>}
    {feedbackError && <p role="status" className="answer-footer">{text("ratingFailed")}</p>}
  </article>;
}
