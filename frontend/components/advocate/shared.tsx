"use client";

import { AlertTriangle, Check, ClipboardCopy, Download, ExternalLink, FileText } from "lucide-react";
import { useCallback, useState, type ReactNode } from "react";

import SourceInspector from "@/components/SourceInspector";
import { ApiError } from "@/lib/api";
import { coverageLines, currencyMeta, draftExportText, exportFilename, type Tone } from "@/lib/advocate-presentation";
import { docxFilename, saveDocx, textToBlocks } from "@/lib/docx";
import type { AdvocateSource, CheckRow, CoverageStatement, VerifiedClaim } from "@/lib/types-advocate";

export function errorText(error: unknown): string {
  return error instanceof ApiError ? error.message : "That did not work. Check the backend and try again.";
}

export function Badge({ tone, children }: { tone: Tone; children: ReactNode }) {
  return <span className={`adv-badge adv-tone-${tone}`}>{children}</span>;
}

export function CurrencyBadge({ source }: { source: AdvocateSource }) {
  const meta = currencyMeta(source);
  return <Badge tone={meta.tone}>{meta.label}</Badge>;
}

/** One click to the passage, with its currency in view before the click. */
export function SourceList({ sources }: { sources: AdvocateSource[] }) {
  const [open, setOpen] = useState<AdvocateSource | null>(null);
  const close = useCallback(() => setOpen(null), []);
  if (!sources.length) return null;
  return (
    <>
      <div className="adv-sources">
        {sources.map((source, index) => (
          <button key={`${source.chunk_id}-${index}`} type="button" className="adv-source" onClick={() => setOpen(source)}>
            <FileText size={12} aria-hidden="true" />
            <span className="adv-source-title">
              {source.section || source.title}
              {source.section ? "" : `, p.${source.page_start}`}
            </span>
            <CurrencyBadge source={source} />
          </button>
        ))}
      </div>
      {open && <SourceInspector source={open} onClose={close} />}
    </>
  );
}

export function ClaimList({ claims, ordered = false }: { claims: VerifiedClaim[]; ordered?: boolean }) {
  const List = ordered ? "ol" : "ul";
  return (
    <List className="adv-list">
      {claims.map((claim, index) => (
        <li key={index} className="adv-card">
          <p>{ordered ? `${index + 1}. ` : ""}{claim.text}</p>
          <SourceList sources={claim.citations} />
        </li>
      ))}
    </List>
  );
}

/**
 * Printed on every result that rests on the judgment set. Against a small set a
 * tool like this appears to work, so the size of the set stays in view.
 */
export function CoverageBanner({ coverage, label }: { coverage: CoverageStatement | null | undefined; label?: string }) {
  const [statement, absence] = coverageLines(coverage);
  return (
    <div className="adv-notice" role="note">
      {label && <strong>{label}</strong>}
      <span>{statement}</span>
      <strong>{absence}</strong>
    </div>
  );
}

const FINDING_TONE: Record<string, { label: string; tone: Tone }> = {
  still_current: { label: "In force", tone: "ok" },
  renumbered: { label: "Renumbered", tone: "warn" },
  elements_changed: { label: "Changed", tone: "warn" },
  not_re_enacted: { label: "Repealed, no successor", tone: "bad" },
  no_mapping_known: { label: "No counterpart listed", tone: "warn" },
  not_checked: { label: "Not checked", tone: "neutral" },
};

export function CheckRows({ rows, empty }: { rows: CheckRow[]; empty?: string }) {
  if (!rows.length) return empty ? <p className="adv-meta">{empty}</p> : null;
  return (
    <ul className="adv-list">
      {rows.map((row) => {
        const meta = FINDING_TONE[row.finding] ?? FINDING_TONE.not_checked;
        return (
          <li key={row.citation} className="adv-date">
            <span className="adv-grow">
              <strong>{row.citation}</strong>
              <span className="adv-meta" style={{ display: "block" }}>{row.advice}</span>
            </span>
            <Badge tone={meta.tone}>{meta.label}</Badge>
          </li>
        );
      })}
    </ul>
  );
}

export function Notes({ items, tone = "plain" }: { items: string[]; tone?: "plain" | "warn" }) {
  if (!items.length) return null;
  return (
    <div className={`adv-notice ${tone === "plain" ? "is-plain" : ""}`} role="note">
      {items.map((item) => <span key={item}>{item}</span>)}
    </div>
  );
}

export function Bullets({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <div>
      <p className="adv-subhead">{title}</p>
      <ul className="adv-bullets">{items.map((item) => <li key={item}>{item}</li>)}</ul>
    </div>
  );
}

export function DraftActions({ content, title, version }: { content: { rendered_text: string; disclaimer: string }; title: string; version: number }) {
  const [copied, setCopied] = useState(false);
  const [failed, setFailed] = useState(false);
  const text = draftExportText(content);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setFailed(true);
    }
  };
  const save = () => {
    const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = exportFilename(title, version);
    link.click();
    URL.revokeObjectURL(url);
  };
  return (
    <div className="adv-actions">
      <button type="button" className="draft-action" onClick={() => void copy()}>
        {copied ? <Check size={13} /> : <ClipboardCopy size={13} />}{copied ? "Copied" : "Copy"}
      </button>
      <button type="button" className="draft-action" onClick={save}><Download size={13} />Save as text</button>
      <button type="button" className="draft-action" onClick={() => saveDocx(docxFilename(title, version), textToBlocks(text))}><FileText size={13} />Save as Word</button>
      {failed && <span className="adv-error">The browser refused clipboard access. Select the text and copy it instead.</span>}
    </div>
  );
}

export function ExternalSource({ href, children }: { href: string | null | undefined; children: ReactNode }) {
  if (!href) return null;
  return <a className="adv-external" href={href} target="_blank" rel="noopener noreferrer">{children}<ExternalLink size={11} aria-hidden="true" /></a>;
}

export function ErrorLine({ text }: { text: string }) {
  if (!text) return null;
  return <p className="adv-error" role="alert"><AlertTriangle size={13} style={{ display: "inline", marginRight: 4 }} aria-hidden="true" />{text}</p>;
}

export function NeedsCase() {
  return (
    <div className="empty-case">
      <p>Pick a case on the left, or start one. This tool works only on the case you select, and reads no other.</p>
    </div>
  );
}

export function TriSelect({ label, hint, value, onChange }: { label: string; hint?: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="adv-label">
      {label}
      <select className="field" value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">Not recorded</option>
        <option value="yes">Yes</option>
        <option value="no">No</option>
      </select>
      {hint && <small>{hint}</small>}
    </label>
  );
}

export function DateField({ label, hint, value, onChange }: { label: string; hint?: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="adv-label">
      {label}
      <input type="date" className="field" value={value} onChange={(event) => onChange(event.target.value)} />
      {hint && <small>{hint}</small>}
    </label>
  );
}
