"use client";

import { FileText, Loader2, Scale, Users } from "lucide-react";
import { useState } from "react";
import { request } from "@/lib/api";

interface Source { quote: string; title: string; page_start: number; page_end: number }
interface Person { name: string; role: string; source: Source }
interface Conflict { topic: string; first: Source; second: Source }
interface Result<T> { items: T[]; dropped: number; files_read_in_full: boolean }

function Quote({ source }: { source: Source }) {
  return <figure className="mt-2">
    <blockquote className="border-l-2 border-[var(--border)] pl-3 text-sm leading-6">{source.quote}</blockquote>
    <figcaption className="mt-1 flex items-center gap-1.5 pl-3 text-xs text-[var(--ink-soft)]">
      <FileText size={13} aria-hidden="true" />{source.title}, page {source.page_start === source.page_end ? source.page_start : `${source.page_start}–${source.page_end}`}
    </figcaption>
  </figure>;
}

/** Who is who, and where the statements disagree, each entry quoted from the files. */
export default function CaseInsights({ caseId }: { caseId: string }) {
  const [people, setPeople] = useState<Result<Person> | null>(null);
  const [conflicts, setConflicts] = useState<Result<Conflict> | null>(null);
  const [busy, setBusy] = useState<"people" | "conflicts" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async (kind: "people" | "conflicts") => {
    setBusy(kind);
    setError(null);
    try {
      const result = await request<Result<Person & Conflict>>(`/cases/${caseId}/insights/${kind}`, { method: "POST" });
      if (kind === "people") setPeople(result);
      else setConflicts(result);
    } catch {
      setError("That could not be completed. Check the connection and try again.");
    } finally {
      setBusy(null);
    }
  };
  const note = (result: Result<unknown>) => <>
    {!result.files_read_in_full && <p className="text-sm text-[var(--state-warn-text)]">This case is long, so only the first part of its files was read.</p>}
    {result.dropped > 0 && <p className="text-xs text-[var(--ink-soft)]">{result.dropped} {result.dropped === 1 ? "entry was" : "entries were"} left out because the quotation could not be found in the files.</p>}
  </>;

  return <section aria-label="Case insights" className="space-y-6">
    <p className="text-sm text-[var(--ink-soft)]">Every quotation here was found word for word in the case files, but the reading is the model&apos;s. Treat these as leads to check, not findings.</p>
    {error && <p role="alert" className="text-sm text-[var(--state-bad-text)]">{error}</p>}

    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 font-semibold"><Users size={16} aria-hidden="true" />Who&apos;s who</h3>
        <button className="button-secondary inline-flex items-center gap-2" disabled={busy !== null} onClick={() => void run("people")}>
          {busy === "people" && <Loader2 size={15} className="animate-spin" aria-hidden="true" />}{busy === "people" ? "Reading, about a minute" : people ? "Read again" : "Find people"}
        </button>
      </div>
      {people && note(people)}
      {people && !people.items.length && <p className="text-sm text-[var(--ink-soft)]">No named people could be confirmed in the files.</p>}
      <ul className="space-y-3">{people?.items.map(item => <li key={item.name} className="rounded-lg border border-[var(--border)] bg-[var(--card)] p-3">
        <p className="text-sm font-semibold">{item.name}{item.role && <span className="font-normal text-[var(--ink-soft)]"> · {item.role}</span>}</p>
        <Quote source={item.source} />
      </li>)}</ul>
    </div>

    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 font-semibold"><Scale size={16} aria-hidden="true" />Possible contradictions</h3>
        <button className="button-secondary inline-flex items-center gap-2" disabled={busy !== null} onClick={() => void run("conflicts")}>
          {busy === "conflicts" && <Loader2 size={15} className="animate-spin" aria-hidden="true" />}{busy === "conflicts" ? "Reading, about a minute" : conflicts ? "Read again" : "Compare statements"}
        </button>
      </div>
      {conflicts && note(conflicts)}
      {conflicts && !conflicts.items.length && <p className="text-sm text-[var(--ink-soft)]">No contradictions could be confirmed. That does not mean there are none.</p>}
      <ul className="space-y-3">{conflicts?.items.map((item, index) => <li key={`${item.topic}-${index}`} className="rounded-lg border border-[var(--border)] bg-[var(--card)] p-3">
        <p className="text-sm font-semibold">{item.topic}</p>
        <Quote source={item.first} />
        <Quote source={item.second} />
      </li>)}</ul>
    </div>
  </section>;
}
