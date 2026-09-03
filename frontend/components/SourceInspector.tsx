"use client";

import { CheckCircle2, CircleAlert, FileText, Scale, ShieldCheck, X } from "lucide-react";
import type { SourceEvidence } from "@/lib/types";
import { useEffect, useRef } from "react";

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
  const dialogRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const dialog = dialogRef.current;
    const targets = () => Array.from(dialog?.querySelectorAll<HTMLElement>("button, a[href], [tabindex='0']") ?? []);
    targets()[0]?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      if (event.key === "Tab") {
        const nodes = targets(); const first = nodes[0]; const last = nodes[nodes.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    };
    document.addEventListener("keydown", keydown);
    return () => { document.removeEventListener("keydown", keydown); previous?.focus(); };
  }, [onClose]);
  return (
    <div ref={dialogRef} className="fixed inset-0 z-[80] flex justify-end bg-[#303039]/35 backdrop-blur-[2px]" role="dialog" aria-modal="true" aria-label="Evidence inspector">
      <button className="absolute inset-0 cursor-default" onClick={onClose} aria-label="Close evidence inspector" />
      <aside className="relative flex h-full w-full max-w-[520px] flex-col border-l border-[#dfe5eb] bg-white shadow-[-20px_0_60px_rgba(11,23,41,.18)]">
        <header className="flex items-start justify-between border-b border-[#e9e5ef] px-6 py-5">
          <div><p className="eyebrow">Why did the system say this?</p><h2 className="mt-1 text-xl font-semibold tracking-tight">Evidence inspector</h2></div>
          <button onClick={onClose} className="rounded-xl border border-[#e9e5ef] p-2 text-[#827b8c] hover:bg-[#faf7f2]" aria-label="Close"><X size={18} /></button>
        </header>
        <div className="flex-1 overflow-y-auto p-6">
          <div className="rounded-2xl bg-[#303039] p-5 text-white">
            <div className="flex items-start justify-between gap-4"><span className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/10"><Scale size={18} /></span><span className={`rounded-full px-2.5 py-1 text-[10px] font-semibold ${verified ? "bg-[#1f5f56] text-[#a8eee4]" : "bg-[#684a24] text-[#f5d8a6]"}`}>{source.verification_status}</span></div>
            <h3 className="mt-4 text-base font-semibold">{source.title}</h3>
            <p className="mt-1 text-xs capitalize text-slate-400">{label(source.source_type)} / {source.scope === "private_case" ? "Private case evidence" : "Global legal corpus"}</p>
          </div>

          <dl className="mt-5 grid grid-cols-2 gap-3">
            <div className="rounded-xl border border-[#e9e5ef] p-3"><dt className="text-[10px] font-semibold text-[#75817b]">Act / section</dt><dd className="mt-1 text-xs font-medium text-[#54515d]">{source.section ?? "Not specified"}</dd></div>
            <div className="rounded-xl border border-[#e9e5ef] p-3"><dt className="text-[10px] font-semibold text-[#75817b]">Page / chunk</dt><dd className="mt-1 text-xs font-medium text-[#54515d]">pp. {source.page_start}–{source.page_end} / {source.chunk_id}</dd></div>
            <div className="rounded-xl border border-[#e9e5ef] p-3"><dt className="text-[10px] font-semibold text-[#75817b]">Relevance score</dt><dd className="mt-1 text-xs font-medium text-[#54515d]">{source.relevance_score === null ? "Not recorded" : `${Math.round(source.relevance_score * 100)}%`}</dd></div>
            <div className="rounded-xl border border-[#e9e5ef] p-3"><dt className="text-[10px] font-semibold text-[#75817b]">Current-law status</dt><dd className="mt-1 text-xs font-medium capitalize text-[#54515d]">{label(source.current_status)}</dd></div>
          </dl>

          <section className="mt-5 rounded-2xl border border-[#dce4ea] bg-[#faf7f2] p-5">
            <div className="flex items-center gap-2 text-xs font-semibold text-[#54515d]"><FileText size={15} className="text-[#897499]" />Retrieved passage</div>
            <blockquote className="mt-3 whitespace-pre-wrap text-sm leading-6 text-[#4c5d57]">{source.excerpt}</blockquote>
          </section>

          <div className={`mt-5 flex items-start gap-3 rounded-xl border p-4 ${verified ? "border-[#cce6d7] bg-[#f1faf5]" : "border-[#f0d8ad] bg-[#fff8eb]"}`}>
            {verified ? <CheckCircle2 size={17} className="mt-0.5 shrink-0 text-[#2e6b50]" /> : <CircleAlert size={17} className="mt-0.5 shrink-0 text-[#b7791f]" />}
            <div><p className="text-xs font-semibold text-[#54515d]">{verified ? "Source reference verified" : "Professional verification required"}</p><p className="mt-1 text-xs leading-5 text-[#827b8c]">{source.current_status === "status_unverified" ? "The source is grounded, but its current/superseded legal status has not yet passed consolidation review." : source.scope === "private_case" ? "This passage is private evidence, so current-law status is not applicable." : "Review the passage in its original context before relying on it."}</p></div>
          </div>
        </div>
        <footer className="flex items-center gap-2 border-t border-[#e9e5ef] bg-[#fafbfc] px-6 py-4 text-xs text-[#827b8c]"><ShieldCheck size={14} className="text-[#2e6b50]" />Role and matter scope verified by the server</footer>
      </aside>
    </div>
  );
}
