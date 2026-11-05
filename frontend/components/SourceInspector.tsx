"use client";

import { CheckCircle2, CircleAlert, FileText, ShieldCheck, X } from "lucide-react";
import type { SourceEvidence } from "@/lib/types";
import { useEffect, useRef } from "react";

function label(value: string): string {
  return value.replaceAll("_", " ");
}

export default function SourceInspector({
  source,
  onClose,
}: {
  source: SourceEvidence & { source_url?: string | null };
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
    <div ref={dialogRef} className="inspector-scrim fixed inset-0 z-[80] flex justify-end" role="dialog" aria-modal="true" aria-label="Evidence inspector">
      <button className="absolute inset-0 cursor-default" onClick={onClose} aria-label="Close evidence inspector" />
      <aside className="inspector-panel relative flex h-full w-full max-w-[520px] flex-col border-l border-[var(--border)] bg-[var(--card)]">
        <header className="flex items-start justify-between border-b border-[var(--border)] px-6 py-5">
          <div><p className="eyebrow">Why did the system say this?</p><h2 className="inspector-title">Evidence inspector</h2></div>
          <button onClick={onClose} className="icon-button" aria-label="Close"><X size={18} /></button>
        </header>
        <div className="flex-1 overflow-y-auto p-6">
          <div>
            <div className="flex flex-wrap items-center gap-1.5">
              <span className={`answer-badge ${verified ? "is-ok" : "is-warn"} capitalize`}>{source.verification_status}</span>
              <span className="answer-badge is-plain">{source.scope === "private_case" ? "Private case evidence" : "Global legal corpus"}</span>
            </div>
            <h3 className="inspector-source">{source.title}</h3>
            <p className="mt-1 text-xs capitalize text-[var(--ink-soft)]">{label(source.source_type)}</p>
          </div>

          <dl className="inspector-facts">
            <div><dt>Act / section</dt><dd>{source.section ?? "Not specified"}</dd></div>
            <div><dt>Page / chunk</dt><dd>pp. {source.page_start}–{source.page_end} / {source.chunk_id}</dd></div>
            <div><dt>Relevance score</dt><dd>{source.relevance_score === null ? "Not recorded" : `${Math.round(source.relevance_score * 100)}%`}</dd></div>
            <div><dt>Current-law status</dt><dd className="capitalize">{label(source.current_status)}</dd></div>
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
                          <span className="ml-1 rounded bg-[var(--state-warn-bg)] px-1.5 py-0.5 text-xs font-semibold text-[var(--state-bad-text)]">
                            elements changed
                          </span>
                        ) : null}
                        {mapping.note ? (
                          <span className="mt-0.5 block text-xs leading-4 text-[var(--ink-soft)]">
                            {mapping.note}
                          </span>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                ) : null}
                {source.unmapped_repealed_provisions?.length ? (
                  <p className="mt-2 text-xs leading-4 text-[var(--ink-soft)]">
                    No mapping recorded for{" "}
                    {source.unmapped_repealed_provisions.join(", ")}. Check the
                    replacement Act directly.
                  </p>
                ) : null}
                {source.mapping_review_status === "pending_legal_review" ? (
                  <p className="mt-2 text-xs leading-4 text-[var(--ink-soft)]">
                    Section mappings are indicative and awaiting legal review. Confirm
                    against the official concordance before relying on them.
                  </p>
                ) : null}
              </div>
            </div>
          ) : null}

          <section className="mt-5">
            <div className="flex items-center gap-2 text-xs font-semibold text-[var(--ink)]"><FileText size={15} className="text-[var(--accent)]" />Retrieved passage</div>
            <blockquote className="inspector-quote">{source.excerpt}</blockquote>
            {source.source_url && <a className="mt-3 inline-block text-xs font-medium text-[var(--accent)] hover:underline" href={source.source_url} target="_blank" rel="noopener noreferrer">Open the official source</a>}
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
