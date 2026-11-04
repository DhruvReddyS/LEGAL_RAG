"use client";
import { X } from "lucide-react";
import { createPortal } from "react-dom";
import { useDialogFocus } from "../useDialogFocus";
import type { CitizenDocument } from "@/lib/types";
import RedactionReview from "./RedactionReview";
import { useCitizenLang } from "./useCitizenLang";

const PAGE_BREAK = "\n\n\f\n\n";

/** Pages join for review and split back after, so page numbers survive. */
export function joinPages(document: CitizenDocument): string {
  return document.pages.map(page => page.text).join(PAGE_BREAK);
}

export function splitPages(document: CitizenDocument, masked: string): CitizenDocument {
  const parts = masked.split(PAGE_BREAK);
  return { ...document, pages: document.pages.map((page, index) => ({ page: page.page, text: parts[index] ?? "" })) };
}

/** C-02 on the chat attachment path: masking sits between extraction and the question. */
export default function RedactionDialog({ document, onConfirm, onCancel }: { document: CitizenDocument | null; onConfirm: (masked: CitizenDocument) => void; onCancel: () => void }) {
  const ref = useDialogFocus(Boolean(document), onCancel);
  const { t } = useCitizenLang();
  if (!document) return null;
  return createPortal(<div className="modal-backdrop" onMouseDown={onCancel}>
    <div ref={ref} className="ctz-redact-dialog" role="dialog" aria-modal="true" aria-label={t("redactionTitle")} onMouseDown={event => event.stopPropagation()}>
      <button type="button" className="icon-button ctz-dialog-close" aria-label={t("cancel")} onClick={onCancel}><X size={18} aria-hidden="true"/></button>
      <p className="ctz-note">{document.filename}</p>
      <RedactionReview text={joinPages(document)} confirmLabel={t("useMasked")} cancelLabel={t("skipFile")} onCancel={onCancel} onConfirm={masked => onConfirm(splitPages(document, masked))}/>
    </div>
  </div>, window.document.body);
}
