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
    <div ref={dialogRef} className="fixed inset-0 z-[80] flex justify-end bg-[var(--ink)]/35 backdrop-blur-[2px]" role="dialog" aria-modal="true" aria-label="Evidence inspector">
      <button className="absolute inset-0 cursor-default" onClick={onClose} aria-label="Close evidence inspector" />
      <aside className="relative flex h-full w-full max-w-[520px] flex-col border-l border-[var(--border)] bg-[var(--card)] shadow-[-20px_0_60px_rgba(11,23,41,.18)]">
        <header className="flex items-start justify-between border-b border-[var(--border)] px-6 py-5">
          <div><p className="eyebrow">Why did the system say this?</p><h2 className="mt-1 text-xl font-semibold tracking-tight">Evidence inspector</h2></div>
          <button onClick={onClose} className="rounded-xl border border-[var(--border)] p-2 text-[var(--ink-soft)] hover:bg-[var(--hover)]" aria-label="Close"><X size={18} /></button>
        </header>
        <div className="flex-1 overflow-y-auto p-6">
          <div className="rounded-2xl bg-[var(--ink)] p-5 text-[var(--paper)]">
            <div className="flex items-start justify-between gap-4"><span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--card)]/10"><Scale size={18} /></span><span className={`rounded-full px-2.5 py-1 text-[10px] font-semibold ${verified ? "bg-[var(--state-ok-text)] text-[var(--state-ok-line)]" : "bg-[var(--state-warn-text)] text-[var(--state-warn-line)]"}`}>{source.verification_status}</span></div>
            <h3 className="mt-4 text-base font-semibold">{source.title}</h3>
            <p className="mt-1 text-xs capitalize text-slate-400">{label(source.source_type)} / {source.scope === "private_case" ? "Private case evidence" : "Global legal corpus"}</p>
          </div>

          <dl className="mt-5 grid grid-cols-2 gap-3">
            <div className="rounded-xl border border-[var(--border)] p-3"><dt className="text-[10px] font-semibold text-[var(--ink-soft)]">Act / section</dt><dd className="mt-1 text-xs font-medium text-[var(--ink)]">{source.section ?? "Not specified"}</dd></div>
            <div className="rounded-xl border border-[var(--border)] p-3"><dt className="text-[10px] font-semibold text-[var(--ink-soft)]">Page / chunk</dt><dd className="mt-1 text-xs font-medium text-[var(--ink)]">pp. {source.page_start}–{source.page_end} / {source.chunk_id}</dd></div>
            <div className="rounded-xl border border-[var(--border)] p-3"><dt className="text-[10px] font-semibold text-[var(--ink-soft)]">Relevance score</dt><dd className="mt-1 text-xs font-medium text-[var(--ink)]">{source.relevance_score === null ? "Not recorded" : `${Math.round(source.relevance_score * 100)}%`}</dd></div>
            <div className="rounded-xl border border-[var(--border)] p-3"><dt className="text-[10px] font-semibold text-[var(--ink-soft)]">Current-law status</dt><dd className="mt-1 text-xs font-medium capitalize text-[var(--ink)]">{label(source.current_status)}</dd></div>
          </dl>

          {/* Two different warnings. Label A says this document is out of
              force; Label B says this document is in force but written against
              a provision that has moved. Merging them would tell a reader to
              disregard guidance that still binds. */}
          {source.repeal_label === "no_longer_in_force" ? (
            <div className="mt-3 flex items-start gap-3 rounded-xl border border-[var(--state-bad-line)] bg-[var(--state-warn-bg)] p-4">
              <CircleAlert size={17} className="mt-0.5 shrink-0 text-[var(--state-bad-text)]" />
              <div>
                <p className="text-xs font-semibold text-[var(--ink)]">
                  No longer in force{source.repealed_on ? ` from ${source.repealed_on}` : ""}
                </p>
                <p className="mt-1 text-xs leading-5 text-[var(--ink-soft)]">
                  {source.replaced_by ? `Replaced by ${source.replaced_by}. ` : ""}
                  It still applies to conduct from before that date, so it may be the
                  right authority for an older matter — but not for anything happening
                  now.
                </p>
              </div>
            </div>
          ) : source.repeal_label === "concerns_repealed_provision" ? (
            <div className="mt-3 flex items-start gap-3 rounded-xl border border-[var(--state-warn-line)] bg-[var(--state-warn-bg)] p-4">
              <CircleAlert size={17} className="mt-0.5 shrink-0 text-[var(--state-warn-text)]" />
              <div>
                <p className="text-xs font-semibold text-[var(--ink)]">
                  Still in force, but cites provisions that have moved
                </p>
                <p className="mt-1 text-xs leading-5 text-[var(--ink-soft)]">
                  This document itself still applies. The provisions it refers to were
                  renumbered on 1 July 2024.
                </p>
                {source.section_mappings?.length ? (
                  <ul className="mt-2 space-y-1">
                    {source.section_mappings.map(mapping => (
                      <li
                        key={`${mapping.from_code}-${mapping.from_section}`}
                        className="text-xs leading-5 text-[var(--ink)]"
                      >
                        <span className="font-medium">
                          {mapping.from_code} s.{mapping.from_section}
                        </span>
                        {" → "}
                        <span className="font-medium">
                          {mapping.to_code} s.{mapping.to_section}
                        </span>
                        {mapping.subject ? (
                          <span className="text-[var(--ink-soft)]"> — {mapping.subject}</span>
                        ) : null}
                        {mapping.ingredients_changed ? (
                          <span className="ml-1 rounded bg-[var(--state-warn-bg)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--state-bad-text)]">
                            elements changed
                          </span>
                        ) : null}
                        {mapping.note ? (
                          <span className="mt-0.5 block text-[11px] leading-4 text-[var(--ink-soft)]">
                            {mapping.note}
                          </span>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                ) : null}
                {source.unmapped_repealed_provisions?.length ? (
                  <p className="mt-2 text-[11px] leading-4 text-[var(--ink-soft)]">
                    No mapping recorded for{" "}
                    {source.unmapped_repealed_provisions.join(", ")}. Check the
                    replacement Act directly.
                  </p>
                ) : null}
                {source.mapping_review_status === "pending_legal_review" ? (
                  <p className="mt-2 text-[11px] leading-4 text-[var(--ink-soft)]">
                    Section mappings are indicative and awaiting legal review. Confirm
                    against the official concordance before relying on them.
                  </p>
                ) : null}
              </div>
            </div>
          ) : null}

          <section className="mt-5 rounded-2xl border border-[var(--border)] bg-[var(--hover)] p-5">
            <div className="flex items-center gap-2 text-xs font-semibold text-[var(--ink)]"><FileText size={15} className="text-[var(--accent)]" />Retrieved passage</div>
            <blockquote className="mt-3 whitespace-pre-wrap text-sm leading-6 text-[var(--ink-soft)]">{source.excerpt}</blockquote>
          </section>

          <div className={`mt-5 flex items-start gap-3 rounded-xl border p-4 ${verified ? "border-[var(--state-ok-line)] bg-[var(--state-ok-bg)]" : "border-[var(--state-warn-line)] bg-[var(--state-warn-bg)]"}`}>
            {verified ? <CheckCircle2 size={17} className="mt-0.5 shrink-0 text-[var(--state-ok-text)]" /> : <CircleAlert size={17} className="mt-0.5 shrink-0 text-[var(--state-warn-text)]" />}
            <div><p className="text-xs font-semibold text-[var(--ink)]">{verified ? "Source reference verified" : "Professional verification required"}</p><p className="mt-1 text-xs leading-5 text-[var(--ink-soft)]">{source.repeal_label === "no_longer_in_force" ? "This Act is no longer in force. Check the replacement named above before relying on it for anything current." : source.repeal_label === "concerns_repealed_provision" ? "This document is still in force, but the provisions it cites were renumbered on 1 July 2024. The new numbering is listed above." : source.current_status === "status_unverified" ? "The source is grounded, but its current/superseded legal status has not yet passed consolidation review." : source.scope === "private_case" ? "This passage is private evidence, so current-law status is not applicable." : "Review the passage in its original context before relying on it."}</p></div>
          </div>
        </div>
        <footer className="flex items-center gap-2 border-t border-[var(--border)] bg-[var(--card)] px-6 py-4 text-xs text-[var(--ink-soft)]"><ShieldCheck size={14} className="text-[var(--state-ok-text)]" />Role and matter scope verified by the server</footer>
      </aside>
    </div>
  );
}
