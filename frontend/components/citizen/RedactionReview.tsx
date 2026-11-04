"use client";
import { Eraser, ShieldCheck } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { applyMasks, countByKind, detectSensitive, segments, type ManualMask, type SensitiveKind, type SensitiveSpan } from "@/lib/citizen-redact";
import { useCitizenLang } from "./useCitizenLang";

/**
 * C-02. Shows the text with what we found highlighted. Nothing here reaches the
 * network: the parent only gets the masked text when the person confirms.
 */
export default function RedactionReview({ text, confirmLabel, onConfirm, onCancel, cancelLabel }: { text: string; confirmLabel: string; onConfirm: (masked: string, maskCount: number) => void; onCancel?: () => void; cancelLabel?: string }) {
  const { t } = useCitizenLang();
  const detected = useMemo(() => detectSensitive(text), [text]);
  const [spans, setSpans] = useState<SensitiveSpan[]>(detected);
  const [manual, setManual] = useState<ManualMask[]>([]);
  const [hint, setHint] = useState("");
  const area = useRef<HTMLDivElement>(null);
  const counts = countByKind(spans.filter(span => span.masked));
  const parts = useMemo(() => segments(text, spans), [text, spans]);

  // Selection offsets are measured against the rendered text, which is the
  // original text with its characters in order, so they line up with `text`.
  const maskSelection = () => {
    const selection = window.getSelection();
    const root = area.current;
    if (!selection || selection.isCollapsed || !root || !root.contains(selection.anchorNode) || !root.contains(selection.focusNode)) { setHint(t("selectFirst")); return; }
    const range = selection.getRangeAt(0);
    const before = document.createRange();
    before.selectNodeContents(root);
    before.setEnd(range.startContainer, range.startOffset);
    const start = before.toString().length;
    const end = start + range.toString().length;
    if (end <= start) { setHint(t("selectFirst")); return; }
    setManual(current => [...current, { start, end }]);
    selection.removeAllRanges();
    setHint("");
  };

  const isManual = (start: number, end: number) => manual.some(mask => start < mask.end && mask.start < end);

  return <section className="ctz-redact" aria-label={t("redactionTitle")}>
    <h3><ShieldCheck size={17} aria-hidden="true"/>{t("redactionTitle")}</h3>
    <p className="ctz-note">{spans.length ? t("redactionLead") : t("redactionNone")}</p>
    {!!Object.keys(counts).length && <ul className="ctz-redact-counts">{(Object.entries(counts) as [SensitiveKind, number][]).map(([kind, count]) => <li key={kind}>{t(`kind_${kind}`)} · {count}</li>)}</ul>}
    <div ref={area} className="ctz-redact-text" tabIndex={0} aria-label={t("noticeTextLabel")}>
      {parts.map((part, index) => part.span
        ? <button type="button" key={part.span.id} className={`ctz-mask ${part.span.masked ? "is-masked" : "is-kept"}`} aria-pressed={part.span.masked} aria-label={`${t(`kind_${part.span.kind}`)}: ${part.span.masked ? t("masked") : t("kept")}`} onClick={() => setSpans(current => current.map(item => item.id === part.span!.id ? { ...item, masked: !item.masked } : item))}>{part.text}</button>
        : <ManualText key={index} text={part.text} offset={offsetOf(parts, index)} isManual={isManual}/>)}
    </div>
    <div className="ctz-actions">
      <button type="button" className="ctz-btn ctz-btn-quiet" onMouseDown={event => event.preventDefault()} onClick={maskSelection}><Eraser size={15} aria-hidden="true"/>{t("maskSelected")}</button>
      {!!manual.length && <button type="button" className="ctz-link" onClick={() => setManual([])}>{t("undoManual")}</button>}
    </div>
    {hint && <p className="ctz-note" role="status">{hint}</p>}
    <div className="ctz-actions">
      <button type="button" className="button-primary ctz-primary" onClick={() => onConfirm(applyMasks(text, spans, manual), spans.filter(span => span.masked).length + manual.length)}>{confirmLabel}</button>
      {onCancel && <button type="button" className="ctz-link" onClick={onCancel}>{cancelLabel ?? t("cancel")}</button>}
    </div>
  </section>;
}

function offsetOf(parts: { text: string }[], index: number): number {
  return parts.slice(0, index).reduce((total, part) => total + part.text.length, 0);
}

function ManualText({ text, offset, isManual }: { text: string; offset: number; isManual: (start: number, end: number) => boolean }) {
  if (!isManual(offset, offset + text.length)) return <span>{text}</span>;
  const pieces: { text: string; masked: boolean }[] = [];
  let run = "";
  let masked = isManual(offset, offset + 1);
  for (let index = 0; index < text.length; index += 1) {
    const next = isManual(offset + index, offset + index + 1);
    if (next !== masked) { pieces.push({ text: run, masked }); run = ""; masked = next; }
    run += text[index];
  }
  pieces.push({ text: run, masked });
  return <>{pieces.map((piece, index) => piece.masked ? <mark key={index} className="ctz-mask is-masked">{piece.text}</mark> : <span key={index}>{piece.text}</span>)}</>;
}
