"use client";

import { CheckCircle2, CircleAlert, FileText, Scale, ShieldCheck, X } from "lucide-react";
import type { SourceEvidence } from "@/lib/types";

function label(value: string): string {
  return value.replaceAll("_", " ");
}

export default function SourceInspector({
  source,
  onClose,
}: {
  source: SourceEvidence;
  onClose: () => void;
}) {
  const verified = source.verification_status === "verified";
  return (
    <div className="fixed inset-0 z-[80] flex justify-end bg-[#0b1729]/35 backdrop-blur-[2px]" role="dialog" aria-modal="true" aria-label="Evidence inspector">
      <button className="absolute inset-0 cursor-default" onClick={onClose} aria-label="Close evidence inspector" />
      <aside className="relative flex h-full w-full max-w-[520px] flex-col border-l border-[#dfe5eb] bg-white shadow-[-20px_0_60px_rgba(11,23,41,.18)]">
        <header className="flex items-start justify-between border-b border-[#e4e7ec] px-6 py-5">
          <div><p className="eyebrow">Why did the system say this?</p><h2 className="mt-1 text-xl font-semibold tracking-tight">Evidence inspector</h2></div>
          <button onClick={onClose} className="rounded-xl border border-[#e4e7ec] p-2 text-[#667085] hover:bg-[#f8fafc]" aria-label="Close"><X size={18} /></button>
        </header>
        <div className="flex-1 overflow-y-auto p-6">
          <div className="rounded-2xl bg-[#0b1729] p-5 text-white">
            <div className="flex items-start justify-between gap-4"><span className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/10"><Scale size={18} /></span><span className={`rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide ${verified ? "bg-[#1f5f56] text-[#a8eee4]" : "bg-[#684a24] text-[#f5d8a6]"}`}>{source.verification_status}</span></div>
            <h3 className="mt-4 text-base font-semibold">{source.title}</h3>
            <p className="mt-1 text-xs capitalize text-slate-400">{label(source.source_type)} · {source.scope === "private_case" ? "Private case evidence" : "Global legal corpus"}</p>
          </div>

          <dl className="mt-5 grid grid-cols-2 gap-3">
            <div className="rounded-xl border border-[#e4e7ec] p-3"><dt className="text-[10px] font-semibold uppercase tracking-wide text-[#98a2b3]">Act / section</dt><dd className="mt-1 text-xs font-medium text-[#344054]">{source.section ?? "Not specified"}</dd></div>
            <div className="rounded-xl border border-[#e4e7ec] p-3"><dt className="text-[10px] font-semibold uppercase tracking-wide text-[#98a2b3]">Page / chunk</dt><dd className="mt-1 text-xs font-medium text-[#344054]">pp. {source.page_start}–{source.page_end} · {source.chunk_id}</dd></div>
            <div className="rounded-xl border border-[#e4e7ec] p-3"><dt className="text-[10px] font-semibold uppercase tracking-wide text-[#98a2b3]">Relevance score</dt><dd className="mt-1 text-xs font-medium text-[#344054]">{source.relevance_score === null ? "Not recorded" : `${Math.round(source.relevance_score * 100)}%`}</dd></div>
            <div className="rounded-xl border border-[#e4e7ec] p-3"><dt className="text-[10px] font-semibold uppercase tracking-wide text-[#98a2b3]">Current-law status</dt><dd className="mt-1 text-xs font-medium capitalize text-[#344054]">{label(source.current_status)}</dd></div>
          </dl>

          <section className="mt-5 rounded-2xl border border-[#dce4ea] bg-[#f8fafc] p-5">
            <div className="flex items-center gap-2 text-xs font-semibold text-[#344054]"><FileText size={15} className="text-[#167184]" />Retrieved passage</div>
            <blockquote className="mt-3 whitespace-pre-wrap text-sm leading-6 text-[#475467]">{source.excerpt}</blockquote>
          </section>

          <div className={`mt-5 flex items-start gap-3 rounded-xl border p-4 ${verified ? "border-[#cce6d7] bg-[#f1faf5]" : "border-[#f0d8ad] bg-[#fff8eb]"}`}>
            {verified ? <CheckCircle2 size={17} className="mt-0.5 shrink-0 text-[#16825d]" /> : <CircleAlert size={17} className="mt-0.5 shrink-0 text-[#b7791f]" />}
            <div><p className="text-xs font-semibold text-[#344054]">{verified ? "Source reference verified" : "Professional verification required"}</p><p className="mt-1 text-xs leading-5 text-[#667085]">{source.current_status === "status_unverified" ? "The source is grounded, but its current/superseded legal status has not yet passed consolidation review." : source.scope === "private_case" ? "This passage is private evidence, so current-law status is not applicable." : "Review the passage in its original context before relying on it."}</p></div>
          </div>
        </div>
        <footer className="flex items-center gap-2 border-t border-[#e4e7ec] bg-[#fafbfc] px-6 py-4 text-xs text-[#667085]"><ShieldCheck size={14} className="text-[#16825d]" />Role and matter scope verified by the server</footer>
      </aside>
    </div>
  );
}
