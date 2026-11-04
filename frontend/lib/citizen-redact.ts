/**
 * C-02: find the personal details in a document's text before anything is sent.
 * This runs in the browser only. It is a helper, not a guarantee: it errs towards
 * flagging too much, and the person can add or remove any mask.
 */

export type SensitiveKind = "aadhaar" | "pan" | "phone" | "email" | "account" | "address";

export type SensitiveSpan = {
  id: string;
  kind: SensitiveKind;
  start: number;
  end: number;
  value: string;
  /** Default on. The person may turn a mask off. */
  masked: boolean;
};

const MASK_LABEL: Record<SensitiveKind | "manual", string> = {
  aadhaar: "[AADHAAR REMOVED]",
  pan: "[PAN REMOVED]",
  phone: "[PHONE REMOVED]",
  email: "[EMAIL REMOVED]",
  account: "[ACCOUNT NUMBER REMOVED]",
  address: "[ADDRESS REMOVED]",
  manual: "[REMOVED]",
};

const EMAIL = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g;
const PAN = /\b[A-Za-z]{5}\d{4}[A-Za-z]\b/g;
// 12 digits, however they are grouped. Aadhaar never starts with 0 or 1.
const AADHAAR = /(?<![\d-])[2-9]\d{3}[\s-]?\d{4}[\s-]?\d{4}(?![\d-])/g;
// 16-digit cards and a masked VID look like this too: they are account-like.
const LONG_GROUPED = /(?<![\d-])\d{4}[\s-]\d{4}[\s-]\d{4}[\s-]\d{4}(?![\d-])/g;
const PHONE = /(?<![\d-])(?:\+?91[\s-]?|0)?(?:[6-9]\d{4}[\s-]?\d{5}|[6-9]\d{2}[\s-]?\d{3}[\s-]?\d{4})(?![\d-])/g;
// An account number has no shape of its own, so it needs a word beside it.
const ACCOUNT_LABELLED =
  /(?:a\/c|acct|account|khata|खाता|ఖాతా|upi\s*id|ifsc|card)(?:\s*(?:no\.?|number|num|#|संख्या|నంబర్))?\s*[:.\-]?\s*([A-Za-z0-9@._-]*\d[A-Za-z0-9@._-]{5,})/gi;
const IFSC = /\b[A-Za-z]{4}0[A-Za-z0-9]{6}\b/g;

const ADDRESS_LABEL = /^\s*(?:address|addr\.?|resident of|r\/o|residing at|पता|చిరునామా)\s*[:.\-]?\s*(.+)$/gim;
const ADDRESS_LINE =
  /^.*\b(?:h\.?\s?no\.?|house\s+no\.?|door\s+no\.?|d\.?\s?no\.?|flat\s+no\.?|plot\s+no\.?|street|road|lane|colony|nagar|apartments?|layout|sector|mandal|taluk|pin(?:\s*code)?\s*[:.\-]?\s*\d{6})\b.*$/gim;
const PIN_ONLY = /\b(?:pin(?:\s*code)?\s*[:.\-]?\s*)?[1-9]\d{5}\b/gi;

function collect(pattern: RegExp, text: string, kind: SensitiveKind, group = 0): Omit<SensitiveSpan, "id" | "masked">[] {
  const found: Omit<SensitiveSpan, "id" | "masked">[] = [];
  for (const match of text.matchAll(pattern)) {
    const value = match[group];
    if (!value) continue;
    const start = (match.index ?? 0) + (group ? match[0].lastIndexOf(value) : 0);
    found.push({ kind, start, end: start + value.length, value });
  }
  return found;
}

function digits(value: string): string {
  return value.replace(/\D/g, "");
}

/** Spans in reading order, with no overlaps. Earlier in this list wins a tie. */
export function detectSensitive(text: string): SensitiveSpan[] {
  // Sixteen grouped digits first: the first twelve of a card also look like Aadhaar.
  const accepted: Omit<SensitiveSpan, "id" | "masked">[] = collect(LONG_GROUPED, text, "account");
  const candidates = [
    ...collect(EMAIL, text, "email"),
    ...collect(AADHAAR, text, "aadhaar"),
    ...collect(PAN, text, "pan").filter(item => /\d/.test(item.value)),
    ...collect(PHONE, text, "phone").filter(item => digits(item.value).length >= 10),
    ...collect(ACCOUNT_LABELLED, text, "account", 1),
    ...collect(IFSC, text, "account"),
    ...collect(ADDRESS_LABEL, text, "address", 1),
    ...collect(ADDRESS_LINE, text, "address"),
  ];
  // A full address line swallows the phone inside it, which would hide one
  // detail in another. Narrow spans win, and address is what is left around them.
  const priority: SensitiveKind[] = ["email", "aadhaar", "pan", "phone", "account", "address"];
  // The label's own capture is narrower than its whole line, so it goes first.
  const ranked = candidates.sort((a, b) => priority.indexOf(a.kind) - priority.indexOf(b.kind) || (a.end - a.start) - (b.end - b.start) || a.start - b.start);
  for (const candidate of ranked) {
    const overlapping = accepted.filter(item => candidate.start < item.end && item.start < candidate.end);
    if (overlapping.length) {
      if (candidate.kind !== "address" || overlapping.some(item => item.kind === "address")) continue;
      // Keep the parts of an address line outside what was already taken.
      let cursor = candidate.start;
      const inside = [...overlapping].sort((a, b) => a.start - b.start);
      for (const item of [...inside, { start: candidate.end, end: candidate.end }]) {
        const piece = text.slice(cursor, item.start);
        if (piece.trim().length > 2) {
          const offset = piece.length - piece.trimStart().length;
          const start = cursor + offset;
          const value = piece.trim();
          accepted.push({ kind: "address", start, end: start + value.length, value });
        }
        cursor = Math.max(cursor, item.end);
      }
      continue;
    }
    accepted.push(candidate);
  }
  // A bare six-digit PIN on its own line, only near an address already found.
  for (const pin of collect(PIN_ONLY, text, "address")) {
    if (accepted.some(item => pin.start < item.end && item.start < pin.end)) continue;
    // "Cheque no. 123456" is a reference the explanation needs, not a PIN.
    if (/(?:\bno\.?|number|#)\s*$/i.test(text.slice(Math.max(0, pin.start - 10), pin.start))) continue;
    if (accepted.some(item => item.kind === "address" && Math.abs(item.end - pin.start) < 80)) accepted.push(pin);
  }
  return accepted
    .sort((a, b) => a.start - b.start)
    .map((item, index) => ({ ...item, id: `${item.kind}-${item.start}-${index}`, masked: true }));
}

export type ManualMask = { start: number; end: number };

/** Replace masked spans, back to front so offsets stay valid. */
export function applyMasks(text: string, spans: Pick<SensitiveSpan, "start" | "end" | "kind" | "masked">[], manual: ManualMask[] = []): string {
  const all = [
    ...spans.filter(span => span.masked).map(span => ({ start: span.start, end: span.end, label: MASK_LABEL[span.kind] })),
    ...manual.map(span => ({ start: span.start, end: span.end, label: MASK_LABEL.manual })),
  ].sort((a, b) => a.start - b.start);
  const merged: typeof all = [];
  for (const item of all) {
    const last = merged[merged.length - 1];
    if (last && item.start < last.end) last.end = Math.max(last.end, item.end);
    else merged.push({ ...item });
  }
  let result = text;
  for (const item of merged.reverse()) {
    result = result.slice(0, item.start) + item.label + result.slice(item.end);
  }
  return result;
}

export type RedactionSegment = { text: string; span?: SensitiveSpan };

/** Text broken up for display, so a highlight never needs inner HTML. */
export function segments(text: string, spans: SensitiveSpan[]): RedactionSegment[] {
  const out: RedactionSegment[] = [];
  let cursor = 0;
  for (const span of [...spans].sort((a, b) => a.start - b.start)) {
    if (span.start < cursor) continue;
    if (span.start > cursor) out.push({ text: text.slice(cursor, span.start) });
    out.push({ text: text.slice(span.start, span.end), span });
    cursor = span.end;
  }
  if (cursor < text.length) out.push({ text: text.slice(cursor) });
  return out;
}

export function countByKind(spans: SensitiveSpan[]): Partial<Record<SensitiveKind, number>> {
  const counts: Partial<Record<SensitiveKind, number>> = {};
  for (const span of spans) counts[span.kind] = (counts[span.kind] ?? 0) + 1;
  return counts;
}
