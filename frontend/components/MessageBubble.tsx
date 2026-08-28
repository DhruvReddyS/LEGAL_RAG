"use client";

import { Bot, BrainCircuit, CheckCircle2, Clock3, ExternalLink, Route, ShieldAlert, User, Zap } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import SourceInspector from "@/components/SourceInspector";
import { useState } from "react";
import type { ChatMessage, SourceEvidence } from "@/lib/types";

interface MessageBubbleProps {
  message: ChatMessage;
}

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1 px-1 py-2">
      <span className="typing-dot h-2 w-2 rounded-full bg-gray-400" />
      <span className="typing-dot h-2 w-2 rounded-full bg-gray-400" />
      <span className="typing-dot h-2 w-2 rounded-full bg-gray-400" />
    </div>
  );
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const [inspector, setInspector] = useState<SourceEvidence | null>(null);
  const totalMs = typeof message.timingsMs?.api_total_ms === "number" ? message.timingsMs.api_total_ms : null;

  return (<>
    <article className={`flex gap-4 rounded-2xl px-5 py-5 ${isUser ? "ml-auto max-w-[82%] bg-[#e9eef4]" : "panel"}`}>
      <div
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
          isUser ? "bg-white text-[#475467]" : "bg-[#0b1729] text-white"
        }`}
      >
        {isUser ? (
          <User size={16} />
        ) : (
          <Bot size={16} />
        )}
      </div>

      <div className="min-w-0 flex-1 pt-0.5">
          <p className="mb-2 text-xs font-semibold text-[#475467]">
          {isUser ? "Your question" : message.agentLabel ?? "Aegis grounded analysis"}
        </p>

        {message.loading ? (
          <div className="flex items-center gap-3 py-2 text-sm text-[#667085]">
            <TypingIndicator />
            {message.requestedMode === "auto" ? "Assessing complexity and selecting the optimal workflow…" : message.requestedMode === "fast" ? "Locating verified corpus authorities…" : "Multi-agent retrieval and verification in progress…"}
          </div>
        ) : message.error ? (
          <div className="rounded-xl border border-[#fecdca] bg-[#fef3f2] px-4 py-3 text-sm text-[#b42318]">
            {message.error}
          </div>
        ) : (
          <>
            <p className="whitespace-pre-wrap text-sm leading-7 text-[#344054]">
              {message.content}
            </p>

            {message.evidenceStrength && (
              <div className="mt-4 flex flex-wrap items-center gap-2"><Badge variant={message.evidenceStrength}>{message.evidenceStrength} evidence · {Math.round((message.confidenceScore ?? 0) * 100)}%</Badge>{message.citations?.length ? <span className="flex items-center gap-1 text-[11px] text-[#16825d]"><CheckCircle2 size={12} /> Citation trail verified</span> : <span className="flex items-center gap-1 text-[11px] text-[#b54708]"><ShieldAlert size={12} /> Safe abstention · no authority published</span>}{message.responseMode && <span className="flex items-center gap-1 rounded-full bg-[#f2f4f7] px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-[#475467]">{message.responseMode === "fast" ? <Zap size={11} /> : <BrainCircuit size={11} />}{message.responseMode}</span>}{message.requestedMode === "auto" && <span className="flex items-center gap-1 rounded-full bg-[#eef6f7] px-2 py-1 text-[10px] font-semibold text-[#167184]" title={(message.routingSignals ?? []).join(", ")}><Route size={11} />Auto-routed · {message.routingReason === "focused_authority_lookup" ? "focused lookup" : "complex analysis"}</span>}{totalMs !== null && <span className={`flex items-center gap-1 rounded-full px-2 py-1 text-[10px] font-semibold ${message.targetMet === false ? "bg-[#fff4ed] text-[#b54708]" : "bg-[#eef8f2] text-[#16734a]"}`}><Clock3 size={11} />{(totalMs / 1000).toFixed(2)}s{message.targetMet !== null && message.targetMet !== undefined ? message.targetMet ? " · target met" : " · target missed" : ""}</span>}</div>
            )}

            {message.citations && message.citations.length > 0 && (
              <div className="mt-5 border-t border-[#eaecf0] pt-4"><p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#667085]">Authorities cited</p><div className="space-y-2">
                {message.citations.map((citation) => (
                  <details key={citation.chunk_id} className="group rounded-xl border border-[#e4e7ec] bg-[#f9fafb] p-3.5">
                    <summary className="flex cursor-pointer list-none items-start gap-3 text-sm font-medium text-[#344054]">
                      <span className="flex h-6 min-w-6 items-center justify-center rounded-md bg-[#e7f2f3] text-[11px] font-semibold text-[#167184]">{citation.number}</span><span className="flex-1">{citation.title}<span className="mt-1 block text-xs font-normal text-[#667085]">Pages {citation.page_start}–{citation.page_end}</span></span><ExternalLink size={14} className="mt-1 text-[#98a2b3]" />
                    </summary>
                    <p className="ml-9 mt-3 whitespace-pre-wrap border-l-2 border-[#c7e2e5] pl-3 text-xs leading-5 text-[#667085]">
                      {citation.excerpt}
                    </p>
                    <button onClick={() => setInspector({ point_id: citation.chunk_id, chunk_id: citation.chunk_id, title: citation.title, source_type: citation.source_type, section: citation.section ?? null, page_start: citation.page_start, page_end: citation.page_end, excerpt: citation.excerpt, relevance_score: citation.retrieval_score ?? null, verification_status: citation.verification_status ?? "unverified", current_status: citation.current_status ?? "status_unverified", scope: "global" })} className="ml-9 mt-3 inline-flex items-center gap-1.5 rounded-lg border border-[#c9dfe2] bg-white px-2.5 py-1.5 text-[10px] font-semibold text-[#167184] hover:bg-[#eef7f8]"><ExternalLink size={12} />Why this source?</button>
                  </details>
                ))}</div></div>
            )}
          </>
        )}
      </div>
    </article>
    {inspector && <SourceInspector source={inspector} onClose={() => setInspector(null)} />}
  </>);
}
