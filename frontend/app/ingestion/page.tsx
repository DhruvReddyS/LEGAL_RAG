"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getIngestionStatus } from "@/lib/api";
import type { IngestionStatus } from "@/lib/types";

const POLL_MS = 5000;

const LABELS: Record<IngestionStatus["status"], string> = {
  not_started: "Not started",
  in_progress: "In progress",
  complete: "Complete",
};

function formatUpdated(value: string | null): string {
  if (!value) return "No checkpoint written yet";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

export default function IngestionStatusPage() {
  const [status, setStatus] = useState<IngestionStatus | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  // Held in a ref so the polling effect does not re-subscribe on every tick.
  const isRunning = useRef(true);

  const load = useCallback(async () => {
    try {
      const next = await getIngestionStatus();
      setStatus(next);
      setError("");
      // Polling exists to watch a run finish. Once it has, stop asking.
      isRunning.current = next.status === "in_progress";
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not reach the backend.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = setInterval(() => {
      if (isRunning.current) void load();
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [load]);

  const rows: [string, string][] = status
    ? [
        ["Documents indexed", `${status.completed_documents} of ${status.total_documents}`],
        ["Remaining", String(status.remaining_documents)],
        ["Checkpoint written", formatUpdated(status.updated_at)],
      ]
    : [];

  return (
    <main className="mx-auto max-w-[720px] px-6 py-12 sm:px-10">
      <header className="border-b border-[var(--border)] pb-6">
        <p className="eyebrow">Corpus</p>
        <h1 className="mt-2 text-3xl">Ingestion status</h1>
        <p className="mt-2 text-sm text-[var(--ink-soft)]">
          Progress of the legal corpus build, read from the ingestion checkpoint.
          Refreshes every {POLL_MS / 1000} seconds while a run is in progress.
        </p>
      </header>

      {loading && (
        <p role="status" className="mt-8 text-sm text-[var(--ink-soft)]">
          Loading ingestion status…
        </p>
      )}

      {error && !loading && (
        <div className="mt-8 rounded-[10px] border border-[var(--border)] bg-[var(--card)] p-5">
          <p role="alert" className="text-sm text-[var(--ink)]">
            {error}
          </p>
          <button
            type="button"
            onClick={() => void load()}
            className="mt-4 rounded-[8px] border border-[var(--border)] px-3 py-1.5 text-sm hover:bg-[var(--hover)]"
          >
            Try again
          </button>
        </div>
      )}

      {status && !error && (
        <section className="mt-8">
          <div className="flex items-baseline justify-between gap-4">
            {/* State is named in words, not signalled by colour alone. */}
            <p className="text-lg font-semibold">{LABELS[status.status]}</p>
            <p className="text-2xl tabular-nums">{status.percent}%</p>
          </div>

          <div
            role="progressbar"
            aria-valuenow={status.percent}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="Documents indexed"
            className="mt-3 h-2 w-full overflow-hidden rounded-full bg-[var(--hover)]"
          >
            <div
              className="h-full rounded-full bg-[var(--accent)]"
              style={{ width: `${Math.min(Math.max(status.percent, 0), 100)}%` }}
            />
          </div>

          <dl className="mt-7 divide-y divide-[var(--border)] border-y border-[var(--border)]">
            {rows.map(([label, value]) => (
              <div key={label} className="flex justify-between gap-6 py-3 text-sm">
                <dt className="text-[var(--ink-soft)]">{label}</dt>
                <dd className="tabular-nums">{value}</dd>
              </div>
            ))}
          </dl>

          {status.status !== "in_progress" && (
            <button
              type="button"
              onClick={() => void load()}
              className="mt-6 rounded-[8px] border border-[var(--border)] px-3 py-1.5 text-sm hover:bg-[var(--hover)]"
            >
              Refresh
            </button>
          )}
        </section>
      )}

      <footer className="mt-12 border-t border-[var(--border)] pt-6 text-xs text-[var(--ink-soft)]">
        <a href="/" className="underline underline-offset-4">
          Return to the application
        </a>
      </footer>
    </main>
  );
}
