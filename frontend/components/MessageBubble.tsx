"use client";
import { BookMarked, Check, Clock3, Copy, Gavel, Pencil, RotateCcw, ShieldCheck, ThumbsDown, ThumbsUp, Volume2, Square, X } from "lucide-react";
import { Fragment, ReactNode, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { presentAnswer } from "@/lib/answer-presentation";
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

export function CorpusilThinking({ detail, deep = true, stageLabel, progress, startedAt }: { detail?: string; deep?: boolean; stageLabel?: string | null; progress?: number | null; startedAt?: number }) {
  const [phrase, setPhrase] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const phrases = deep ? ["Working through your question", "Looking for supporting authority", "Taking a closer look at the evidence"] : ["Finding relevant sources", "Looking for a useful passage"];
  useEffect(() => { const timer = window.setInterval(() => setPhrase(value => value + 1), 3600); return () => window.clearInterval(timer); }, []);
  // Deep review takes minutes. Without an elapsed time and a named stage the
  // wait is indistinguishable from a hang, which is what it was reported as.
  useEffect(() => {
    if (!deep || !startedAt) return;
    const tick = () => setElapsed(Math.floor((Date.now() - startedAt) / 1000));
    tick();
    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, [deep, startedAt]);
  const clock = elapsed >= 60 ? `${Math.floor(elapsed / 60)}m ${String(elapsed % 60).padStart(2, "0")}s` : `${elapsed}s`;
  const scene = phrase % 3;
  return <div className="thinking-inline" role="status" aria-label={deep ? "Deep review in progress" : "Source search in progress"}><div className="thinking-scene" aria-hidden="true">
    {scene === 0 && <div className="balance-mark"><span className="balance-beam"/><span className="balance-pillar"/><span className="balance-pan left"><i className="balance-weight left"/></span><span className="balance-pan right"><i className="balance-weight right"/></span></div>}
    {scene === 1 && <div className="gavel-mark"><Gavel size={24}/><span/></div>}
    {scene === 2 && <div className="authority-mark"><BookMarked size={24}/><span/><i/></div>}
  </div><div className="thinking-copy">
    <p key={stageLabel || phrase}>{stageLabel || phrases[phrase % phrases.length]}…</p>
    {deep && startedAt ? <small>{typeof progress === "number" ? `${progress}% · ` : ""}{clock} elapsed · usually two to five minutes</small> : detail ? <small>{detail}</small> : null}
    {deep && typeof progress === "number" && <div className="thinking-progress" role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100} aria-label="Deep review progress"><span style={{ width: `${Math.max(2, progress)}%` }} /></div>}
  </div></div>;
}

export default function MessageBubble({ message, onRegenerate, onForgetDocuments, onEdit }: { message: ChatMessage; onRegenerate?: () => void; onForgetDocuments?: () => void; onEdit?: (text: string) => void }) {
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
  const presentation = presentAnswer(message.content, {
    fast: message.responseMode === "fast",
    evidenceStrength: message.evidenceStrength ?? null,
  });
  const citations = message.citations ?? [];
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
    return number && citations.some(item => item.number === Number(number)) ? <button key={index} className="source-chip inline-source" aria-label={`Preview source ${number}`} aria-expanded={active === `S${number}`} onClick={() => toggle(`S${number}`)}>{number}</button> : part;
  }) : children;
  const markdown = (text: string) => <ReactMarkdown components={{ p: ({ children }) => <p>{inline(children)}</p>, li: ({ children }) => <li>{inline(children)}</li>, strong: ({ children }) => <strong>{inline(children)}</strong> }}>{text}</ReactMarkdown>;
  const speak = () => {
    window.speechSynthesis.cancel();
    if (speaking) { setSpeaking(false); return; }
    const utterance = new SpeechSynthesisUtterance(presentation.explanation.replace(/\[Source \d+\]|[*#_]/g, ""));
    utterance.lang = "en-IN"; utterance.onend = utterance.onerror = () => setSpeaking(false);
    setSpeaking(true); window.speechSynthesis.speak(utterance);
  };
  if (message.loading) {
    const thinking = <CorpusilThinking deep={(message.responseMode ?? message.requestedMode) === "deep"} stageLabel={message.stageLabel} progress={message.jobProgress} startedAt={message.timestamp} />;
    // A Fast brief exists whenever a low-confidence result escalated. Showing
    // it costs nothing - it was already computed - and replaces a blank
    // multi-minute wait with something the reader can start on.
    if (!message.provisional) return thinking;
    return <div className="provisional-turn">
      {thinking}
      <section className="provisional-brief" aria-label="Provisional evidence, not yet verified">
        <p className="provisional-note"><ShieldCheck size={14}/> Provisional — found by the quick search, not yet checked against your question.</p>
        <div className="legal-answer">{markdown(message.content)}</div>
        {!!citations.length && <div className="trust-row"><span className="source-label">Sources</span>{citations.map(item => <button key={item.chunk_id} className="source-chip" onClick={() => toggle(`S${item.number}`)} aria-expanded={active === `S${item.number}`} aria-label={`Preview source ${item.number}: ${item.title}`}>{item.number}</button>)}</div>}
      </section>
    </div>;
  }
  if (message.role === "user") return <div className={`user-turn ${editing ? "is-editing" : ""}`}><article className="user-message">{editing ? <><textarea autoFocus aria-label="Edit your question" value={editedText} maxLength={4000} rows={3} onChange={event => setEditedText(event.target.value)} onKeyDown={event => { if (event.key === "Escape") setEditing(false); if ((event.metaKey || event.ctrlKey) && event.key === "Enter" && editedText.trim()) { setEditing(false); onEdit?.(editedText.trim()); } }}/><p className="edit-hint">Resending starts a new branch. The original chat stays in history.</p><div className="edit-actions"><button onClick={() => setEditing(false)}>Cancel</button><button disabled={!editedText.trim()} onClick={() => { setEditing(false); onEdit?.(editedText.trim()); }}>Save & resend</button></div></> : <p>{message.content}</p>}{message.documents?.map((doc, index) => <span className="document-chip" key={doc.id}>D{index + 1} · {doc.filename}</span>)}</article>{!editing && <div className="user-actions"><button className="answer-action" aria-label="Copy question" onClick={async () => { try { await navigator.clipboard.writeText(message.content); setCopied(true); } catch { setCopyError(true); } }}>{copied ? <Check size={14}/> : <Copy size={14}/>}</button>{onEdit && <button className="answer-action" aria-label="Edit question" onClick={() => { setEditedText(message.content); setEditing(true); }}><Pencil size={14}/></button>}</div>}{copyError && <p className="edit-hint">Select the text to copy; clipboard access is unavailable.</p>}</div>;
  if (message.stopped) return <div className="stopped-answer"><span>{message.content}</span>{onRegenerate && <button onClick={onRegenerate}><RotateCcw size={13}/>Try again</button>}</div>;
  if (message.error) return <article className="answer-error" role="alert">{message.error}{onRegenerate && <button onClick={onRegenerate}>Try again</button>}</article>;
  return <article className="assistant-message">
    <div className="answer-byline"><span className="corpus-signature">Corpus</span><span>{message.category || "Legal research"}</span></div>
    <div className="answer-lead legal-answer">{markdown(presentation.explanation)}</div>
    <div className="trust-row" aria-label="Evidence and sources">
      <details className="confidence-help"><summary className="confidence-pill">{message.responseMode === "fast" ? "Relevance preview" : message.evidenceStrength === "strong" ? "High confidence" : message.evidenceStrength === "moderate" ? "Moderate confidence" : "Limited evidence"}</summary><p>{message.responseMode === "fast" ? "These passages were retrieved for relevance; their claims have not been verified." : "Confidence describes support in the retrieved sources, not your chance of winning a case. High means strong published evidence support; moderate means some gaps remain. Check the source text and current law."}</p></details>
      {citations.length > 0 && <span className="source-label">Sources</span>}{citations.map(item => <button key={item.chunk_id} className="source-chip" onClick={() => toggle(`S${item.number}`)} aria-expanded={active === `S${item.number}`} aria-label={`Preview source ${item.number}: ${item.title}`}>{item.number}</button>)}
      {!citations.length && <span>No cited authority</span>}
      {message.documents?.map((doc, index) => <button key={doc.id} className="document-chip" onClick={() => toggle(`D${index + 1}`)} aria-expanded={active === `D${index + 1}`} title={`Your document: ${doc.filename}`}>D{index + 1}</button>)}
    </div>
    {(source || document) && <section className={`source-preview ${document ? "document-preview" : ""}`} aria-label="Source preview"><button className="icon-button preview-close" onClick={() => setActive(null)} aria-label="Close source preview"><X size={16}/></button>{source ? <><small>Legal corpus · Source {source.number} · {source.verification_status ?? "Unverified"}</small><h3>{source.title}</h3><p className="source-pages">Pages {source.page_start}–{source.page_end}{source.section ? ` · Section ${source.section}` : ""}</p><blockquote>{source.excerpt}</blockquote></> : document && <><small>Your document · Unverified facts, not legal authority</small><h3>{document.filename}</h3><p className="source-pages">Request context; this chip does not imply a verified legal citation.</p>{document.pages.length ? document.pages.map(page => <div key={page.page}><small>Page {page.page}</small><blockquote>{page.text}</blockquote></div>) : <p>Document text is no longer held in this tab. Reattach it to review.</p>}{onForgetDocuments && <button className="answer-text-action" onClick={() => { onForgetDocuments(); setActive(null); }}>Remove document text from this chat</button>}</>}</section>}
    <div className="legal-answer answer-body">{presentation.basis && <><h3>Legal basis</h3>{markdown(presentation.basis)}</>}{markdown(presentation.other)}{presentation.limits && <details className="answer-limits"><summary>Limits & uncertainties</summary>{markdown(presentation.limits)}</details>}</div>
    <aside className="legal-note" aria-label="Important legal information"><ShieldCheck size={17}/><div><strong>Before you rely on this</strong><p>{citations.length && citations.every(item => item.current_status === "current") ? "These sources are marked current in the corpus, but later changes may apply." : "The current-law status is not independently guaranteed."} Check the latest official text for a live matter. This is legal information, not advice on your circumstances.</p></div></aside>
    <div className="answer-actions" aria-label="Answer actions"><button className="answer-action" aria-label={copied ? "Answer copied" : "Copy answer"} onClick={async () => { try { await navigator.clipboard.writeText(message.content); setCopied(true); setCopyError(false); } catch { setCopyError(true); } }}>{copied ? <Check size={16}/> : <Copy size={16}/>}</button><button className="answer-action" aria-label="Mark answer helpful" aria-pressed={feedback === "up"} disabled={!message.messageId} onClick={() => rate("up")}><ThumbsUp size={16}/></button><button className="answer-action" aria-label="Mark answer not helpful" aria-pressed={feedback === "down"} disabled={!message.messageId} onClick={() => rate("down")}><ThumbsDown size={16}/></button>{onRegenerate && <button className="answer-action" aria-label="Regenerate answer" onClick={onRegenerate}><RotateCcw size={16}/></button>}<span className="performance-pills">{llmElapsedLabel && <span className="answer-performance" title="Measured wall time spent in Ollama calls across this answer." aria-label={`LLM time ${llmElapsedLabel}`}><span>LLM</span>{llmElapsedLabel}</span>}{elapsedLabel && <span className="answer-performance" title="Time from sending your question to receiving the finished response in this tab, including network and review wait." aria-label={`Total response time ${elapsedLabel}`}><Clock3 size={13}/><span>Total</span>{elapsedLabel}</span>}</span>{canSpeak && <button className="listen-button" onClick={speak} aria-pressed={speaking}>{speaking ? <Square size={14}/> : <Volume2 size={16}/>} {speaking ? "Stop reading" : "Listen to answer"}</button>}</div>
    {performanceRows.length > 0 && <details className="rag-timing"><summary><span><Clock3 size={13}/>RAG timing</span>{bottleneck && <small>Slowest: {bottleneck.label} · {durationLabel(bottleneck.ms)}</small>}</summary><div className="rag-timing-list">{performanceRows.map((row, index) => <div key={`${row.label}-${index}`} className={row.detail ? "is-detail" : row.label === "End-to-end total" ? "is-total" : ""}><span>{row.label}</span><b>{durationLabel(row.ms)}</b></div>)}</div></details>}
    {copyError && <p role="status" className="answer-footer">Clipboard unavailable. Select the answer text to copy.</p>}
    {feedbackError && <p role="status" className="answer-footer">Your rating could not be saved. Check your connection and try again.</p>}
  </article>;
}
