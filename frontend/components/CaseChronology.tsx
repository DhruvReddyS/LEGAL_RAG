"use client";

import { CalendarRange, FileText, Loader2, Printer, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { request } from "@/lib/api";

interface ChronologyEvent {
  date: string;
  precision: "day" | "month" | string;
  text: string;
  document_id: string;
  title: string;
  page_start: number;
  page_end: number;
}

interface Chronology {
  events: ChronologyEvent[];
  total_events: number;
  documents_read: number;
}

const DAY = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
const MONTH = new Intl.DateTimeFormat("en-IN", { month: "short", year: "numeric", timeZone: "UTC" });

function readable(event: ChronologyEvent): string {
  return (event.precision === "month" ? MONTH : DAY).format(new Date(`${event.date}T00:00:00Z`));
}

/** What happened when, in the order it happened, from every file in the case. */
export default function CaseChronology({ caseId, onOpenDocuments }: { caseId: string; onOpenDocuments?: () => void }) {
  const [data, setData] = useState<Chronology | null>(null);
  const [error, setError] = useState(false);
  const [filter, setFilter] = useState("");
  const [file, setFile] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    request<Chronology>(`/cases/${caseId}/chronology`, { signal: controller.signal })
      .then(setData)
      .catch(() => { if (!controller.signal.aborted) setError(true); });
    return () => controller.abort();
  }, [caseId]);

  const files = useMemo(() => Array.from(new Set(data?.events.map((event) => event.title))).sort(), [data]);
  const shown = useMemo(() => {
    const wanted = filter.trim().toLowerCase();
    return (data?.events ?? []).filter(
      (event) =>
        (!file || event.title === file) &&
        (!wanted || `${event.text} ${event.title} ${readable(event)}`.toLowerCase().includes(wanted)),
    );
  }, [data, file, filter]);

  if (error) return <p role="alert" className="py-8 text-sm text-[var(--state-bad-text)]">The timeline could not be loaded. Check the connection and try again.</p>;
  if (!data) return <p role="status" className="flex items-center gap-2 py-8 text-sm text-[var(--ink-soft)]"><Loader2 size={16} className="animate-spin" aria-hidden="true" />Reading the case files…</p>;

  if (!data.events.length) {
    return (
      <div className="py-12 text-center">
        <CalendarRange size={26} className="mx-auto text-[var(--ink-soft)]" aria-hidden="true" />
        <h3 className="mt-3 text-base font-semibold">No dates found yet</h3>
        <p className="mx-auto mt-1 max-w-md text-sm text-[var(--ink-soft)]">
          {data.documents_read ? "The files indexed in this case do not state any dates." : "Add and index case files, and the dates they mention will appear here in order."}
        </p>
        {onOpenDocuments && <button className="button-primary mt-4" onClick={onOpenDocuments}>Add case files</button>}
      </div>
    );
  }

  return (
    <section aria-label="Case timeline" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Case timeline</h2>
          <p className="text-sm text-[var(--ink-soft)]">{data.total_events} dated {data.total_events === 1 ? "entry" : "entries"} from {data.documents_read} {data.documents_read === 1 ? "file" : "files"}</p>
        </div>
        <button className="button-secondary inline-flex items-center gap-2 print:hidden" onClick={() => window.print()}><Printer size={15} aria-hidden="true" />Print</button>
      </div>

      <p className="rounded-lg bg-[var(--state-warn-bg)] px-3 py-2 text-sm text-[var(--state-warn-text)]">
        These are dates as written in the files, read day first. A date in a document does not prove the event happened then, so check each entry against its source.
      </p>

      <div className="flex flex-wrap gap-2 print:hidden">
        <label className="flex min-w-56 flex-1 items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--card)] px-3">
          <Search size={15} className="text-[var(--ink-soft)]" aria-hidden="true" />
          <span className="sr-only">Search the timeline</span>
          <input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="Search the timeline" className="h-10 w-full bg-transparent text-sm outline-none" />
        </label>
        {files.length > 1 && (
          <label>
            <span className="sr-only">Show one file</span>
            <select value={file} onChange={(event) => setFile(event.target.value)} className="h-10 max-w-64 rounded-lg border border-[var(--border)] bg-[var(--card)] px-3 text-sm">
              <option value="">All files</option>
              {files.map((name) => <option key={name} value={name}>{name}</option>)}
            </select>
          </label>
        )}
      </div>

      {data.total_events > data.events.length && <p className="text-sm text-[var(--ink-soft)]">Showing the earliest {data.events.length} of {data.total_events} entries.</p>}
      {!shown.length && <p className="py-6 text-sm text-[var(--ink-soft)]">No entries match that search.</p>}

      <ol className="border-l border-[var(--border)]">
        {shown.map((event, index) => (
          <li key={`${event.date}-${event.document_id}-${event.page_start}-${index}`} className="relative py-3 pl-5">
            <span aria-hidden="true" className="absolute -left-[5px] top-[18px] h-[9px] w-[9px] rounded-full bg-[var(--accent)]" />
            <p className="text-sm font-semibold">{readable(event)}</p>
            <p className="mt-1 text-sm leading-6">{event.text}</p>
            <p className="mt-1 flex items-center gap-1.5 text-xs text-[var(--ink-soft)]">
              <FileText size={13} aria-hidden="true" />
              {event.title}, page {event.page_start === event.page_end ? event.page_start : `${event.page_start}–${event.page_end}`}
            </p>
          </li>
        ))}
      </ol>
    </section>
  );
}
