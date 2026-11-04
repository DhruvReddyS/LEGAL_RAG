"use client";

import { AlertTriangle, Loader2 } from "lucide-react";
import type { ReactNode } from "react";

import { ApiError } from "@/lib/api";
import { TRI_WORDS, type Words } from "@/lib/police-presentation";
import type { TriState } from "@/lib/types-police";

export function errorText(error: unknown, fallback = "That could not be done. Check the connection and try again."): string {
  return error instanceof ApiError ? error.message : fallback;
}

export function Pill({ words }: { words: Words }) {
  return <span className={`police-pill is-${words.tone}`}>{words.label}</span>;
}

export function ErrorNote({ message }: { message: string }) {
  if (!message) return null;
  return (
    <p className="police-error" role="alert">
      <AlertTriangle size={14} className="mt-0.5 flex-none" aria-hidden="true" />
      <span>{message}</span>
    </p>
  );
}

export function Loading({ label = "Reading the record…" }: { label?: string }) {
  return (
    <p className="police-loading" role="status">
      <Loader2 size={14} className="animate-spin" aria-hidden="true" />
      {label}
    </p>
  );
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="police-field">
      {label}
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}

/** Three answers, and "not recorded" is one of them rather than the absence of one. */
export function TriToggle({
  label,
  value,
  onChange,
  disabled,
}: {
  label: string;
  value: TriState;
  onChange: (next: TriState) => void;
  disabled?: boolean;
}) {
  const options: TriState[] = ["yes", "no", "unknown"];
  return (
    <span className="police-tri" role="group" aria-label={label}>
      {options.map((option) => (
        <button
          key={option}
          type="button"
          aria-pressed={value === option}
          disabled={disabled}
          onClick={() => onChange(option)}
        >
          {TRI_WORDS[option]}
        </button>
      ))}
    </span>
  );
}
