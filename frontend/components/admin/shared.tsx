"use client";

import { AlertTriangle, Check, CheckCircle2, ChevronLeft, ChevronRight, CircleDashed, Copy, Loader2, X, XCircle } from "lucide-react";
import { ReactNode, useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { ApiError } from "@/lib/api";
import { pageSpan, type Tone } from "@/lib/admin-presentation";
import type { PlanStep } from "@/lib/types-admin";
import { useDialogFocus } from "../useDialogFocus";

export function messageOf(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

/** Load on mount and on change of `key`, keeping the last good data on a refresh. */
export function useLoaded<T>(load: () => Promise<T>, key: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);
  const reload = useCallback(() => setNonce(value => value + 1), []);
  useEffect(() => {
    let active = true;
    setLoading(true);
    load()
      .then(result => {
        if (active) { setData(result); setError(""); }
      })
      .catch(cause => {
        if (active) setError(messageOf(cause, "Could not load this. Check the backend and try again."));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
    // `load` is rebuilt each render; `key` is what actually identifies the request.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, nonce]);
  return { data, error, loading, reload };
}

const TONE_ICONS = {
  ok: CheckCircle2,
  warn: AlertTriangle,
  bad: XCircle,
  neutral: CircleDashed,
} as const;

/** Colour never stands alone: every state also carries an icon and a word. */
export function StatusPill({ tone, children }: { tone: Tone; children: ReactNode }) {
  const Icon = TONE_ICONS[tone];
  return (
    <span className={`admin-pill is-${tone}`}>
      <Icon size={12} aria-hidden="true" />
      {children}
    </span>
  );
}

export function PanelHeading({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return (
    <header className="admin-heading">
      <div>
        <h3>{title}</h3>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className="admin-heading-actions">{actions}</div>}
    </header>
  );
}

export function Notice({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <div role={tone === "bad" ? "alert" : "status"} className={`admin-notice is-${tone}`}>
      {children}
    </div>
  );
}

export function LoadState({ loading, error, empty, onRetry }: { loading: boolean; error: string; empty?: string | null; onRetry?: () => void }) {
  if (error) {
    return (
      <Notice tone="bad">
        <span>{error}</span>
        {onRetry && <button className="admin-link" onClick={onRetry}>Try again</button>}
      </Notice>
    );
  }
  if (loading) {
    return (
      <p className="admin-empty" role="status">
        <Loader2 size={14} className="animate-spin" aria-hidden="true" /> Loading
      </p>
    );
  }
  return empty ? <p className="admin-empty">{empty}</p> : null;
}

export function Pager({ page, pageSize, total, onPage, noun }: { page: number; pageSize: number; total: number; onPage: (page: number) => void; noun: string }) {
  const span = pageSpan(page, pageSize, total);
  return (
    <nav className="admin-pager" aria-label={`${noun} pages`}>
      <span aria-live="polite">
        {total === 0 ? `No ${noun}` : `${span.first} to ${span.last} of ${total.toLocaleString("en-IN")} ${noun}`}
      </span>
      <div>
        <button className="icon-button" aria-label="Previous page" disabled={!span.hasPrevious} onClick={() => onPage(page - 1)}>
          <ChevronLeft size={16} aria-hidden="true" />
        </button>
        <span>Page {page} of {span.pages}</span>
        <button className="icon-button" aria-label="Next page" disabled={!span.hasNext} onClick={() => onPage(page + 1)}>
          <ChevronRight size={16} aria-hidden="true" />
        </button>
      </div>
    </nav>
  );
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="admin-stat">
      <span>{label}</span>
      <strong>{value}</strong>
      {hint && <small>{hint}</small>}
    </div>
  );
}

function CopyCommand({ command }: { command: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="admin-command">
      <code>{command}</code>
      <button
        className="icon-button"
        aria-label={copied ? "Copied" : `Copy ${command}`}
        onClick={() => {
          void navigator.clipboard?.writeText(command).then(() => {
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1500);
          });
        }}
      >
        {copied ? <Check size={14} aria-hidden="true" /> : <Copy size={14} aria-hidden="true" />}
      </button>
    </div>
  );
}

export function Steps({ steps }: { steps: PlanStep[] }) {
  return (
    <ol className="admin-steps">
      {steps.map(step => (
        <li key={step.title}>
          <strong>{step.title}</strong>
          <CopyCommand command={step.command} />
          <p>{step.detail}</p>
        </li>
      ))}
    </ol>
  );
}

export function Dialog({ title, onClose, children, wide }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  const ref = useDialogFocus(true, onClose);
  return createPortal(
    <div className="modal-backdrop" onClick={event => { if (event.target === event.currentTarget) onClose(); }}>
      <div ref={ref} role="dialog" aria-modal="true" aria-label={title} className={`admin-dialog${wide ? " is-wide" : ""}`}>
        <div className="admin-dialog-head">
          <h3>{title}</h3>
          <button className="icon-button" aria-label="Close" onClick={onClose}><X size={16} aria-hidden="true" /></button>
        </div>
        {children}
      </div>
    </div>,
    document.body,
  );
}

/**
 * For an action that needs a deliberate second step. `typed` asks for an exact
 * string; `requireReason` collects a written reason, which is what goes on record.
 */
export function ConfirmDialog({
  title,
  body,
  confirmLabel,
  danger,
  typed,
  requireReason,
  reasonLabel = "Reason",
  minReason = 10,
  onConfirm,
  onClose,
}: {
  title: string;
  body: ReactNode;
  confirmLabel: string;
  danger?: boolean;
  typed?: string;
  requireReason?: boolean;
  reasonLabel?: string;
  minReason?: number;
  onConfirm: (reason: string) => Promise<void>;
  onClose: () => void;
}) {
  const [entry, setEntry] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const ready = (!typed || entry === typed) && (!requireReason || reason.trim().length >= minReason);
  return (
    <Dialog title={title} onClose={onClose}>
      <div className="admin-dialog-body">{body}</div>
      {requireReason && (
        <label className="admin-field">
          <span>{reasonLabel}</span>
          <textarea className="field" rows={3} value={reason} onChange={event => setReason(event.target.value)} />
          <small>
            At least {minReason} characters. Do not paste what a user wrote: this is stored and shown to other administrators.
          </small>
        </label>
      )}
      {typed && (
        <label className="admin-field">
          <span>Type <code>{typed}</code> to confirm</span>
          <input className="field" value={entry} autoComplete="off" spellCheck={false} onChange={event => setEntry(event.target.value)} />
        </label>
      )}
      {error && <Notice tone="bad">{error}</Notice>}
      <div className="admin-dialog-actions">
        <button className="button-secondary" onClick={onClose}>Cancel</button>
        <button
          className={danger ? "button-primary admin-danger" : "button-primary"}
          disabled={!ready || busy}
          onClick={async () => {
            setBusy(true);
            setError("");
            try {
              await onConfirm(reason.trim());
              onClose();
            } catch (cause) {
              setError(messageOf(cause, "That did not complete."));
              setBusy(false);
            }
          }}
        >
          {busy && <Loader2 size={14} className="animate-spin" aria-hidden="true" />}
          {confirmLabel}
        </button>
      </div>
    </Dialog>
  );
}
