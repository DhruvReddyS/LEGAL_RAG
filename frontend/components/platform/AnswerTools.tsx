"use client";

import { FileDown, FileText, Printer } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import {
  answerToHtml,
  answerToMarkdown,
  citationCurrency,
  citationLocation,
  exportFilename,
  NOT_ADVICE,
  safeSourceUrl,
} from "@/lib/answer-export";
import type { ChatMessage } from "@/lib/types";
import { useCitizenLang } from "@/components/citizen/useCitizenLang";

export function saveTextFile(text: string, filename: string, type: string): void {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Print, or save as Markdown or HTML. The sources always come with it. */
export function AnswerExportMenu({ message, question, articleRef, citizen = false }: { message: ChatMessage; question?: string; articleRef: React.RefObject<HTMLElement>; citizen?: boolean }) {
  const { t } = useCitizenLang(citizen);
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent | KeyboardEvent) => {
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !menuRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", close); };
  }, [open]);

  const input = { question, message, exportedAt: new Date() };
  const print = () => {
    setOpen(false);
    const target = articleRef.current;
    if (!target) return;
    target.classList.add("print-target");
    document.body.dataset.printing = "answer";
    const cleanUp = () => {
      target.classList.remove("print-target");
      delete document.body.dataset.printing;
      window.removeEventListener("afterprint", cleanUp);
    };
    window.addEventListener("afterprint", cleanUp);
    window.print();
  };

  return (
    <div className="answer-export" ref={menuRef}>
      <button type="button" className="answer-action" aria-label={t("printOrSave")} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(value => !value)}>
        <FileDown size={16} aria-hidden="true" />
      </button>
      {open && (
        <div className="answer-export-menu" role="menu">
          <button type="button" role="menuitem" autoFocus onClick={print}><Printer size={14} aria-hidden="true" />{t("print")}</button>
          <button type="button" role="menuitem" onClick={() => { setOpen(false); saveTextFile(answerToMarkdown(input), exportFilename("md"), "text/markdown;charset=utf-8"); }}><FileText size={14} aria-hidden="true" />{t("saveMarkdown")}</button>
          <button type="button" role="menuitem" onClick={() => { setOpen(false); saveTextFile(answerToHtml(input), exportFilename("html"), "text/html;charset=utf-8"); }}><FileText size={14} aria-hidden="true" />{t("saveHtml")}</button>
        </div>
      )}
    </div>
  );
}

/** On paper the source panels cannot be opened, so every citation is printed in full. */
export function PrintOnlySources({ message, question }: { message: ChatMessage; question?: string }) {
  const citations = message.citations ?? [];
  return (
    <div className="print-only">
      {question && <p className="print-question"><strong>Question:</strong> {question}</p>}
      <section className="print-sources">
        <h3>Sources</h3>
        {citations.length === 0 && <p>No authority was cited.</p>}
        {citations.map(citation => {
          const url = safeSourceUrl(citation.source_url);
          return (
            <div key={citation.chunk_id} className="print-source">
              <p><strong>[Source {citation.number}] {citation.title}</strong></p>
              <p>{citationLocation(citation)}{citation.verification_status ? ` · Claim check: ${citation.verification_status}` : ""}</p>
              {citationCurrency(citation).map(note => <p key={note}>{note}</p>)}
              {url && <p className="print-url">{url}</p>}
              <blockquote>{citation.excerpt}</blockquote>
            </div>
          );
        })}
      </section>
      <p className="print-note">{NOT_ADVICE}</p>
    </div>
  );
}
