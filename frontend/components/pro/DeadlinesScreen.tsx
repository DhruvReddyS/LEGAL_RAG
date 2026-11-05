"use client";

import { CalendarPlus, Check, RotateCcw } from "lucide-react";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useState } from "react";
import { calendarAcrossCases, updateCalendarEvent } from "@/lib/api-advocate";
import { dayPhrase, eventStateMeta, formatDate, sortEvents } from "@/lib/advocate-presentation";
import type { CalendarEvent } from "@/lib/types-advocate";
import { EmptyState, ErrorState, PageHead, ProLink, RowsLoading, usePro } from "./context";

const DeadlineRegister = dynamic(() => import("@/components/police/DeadlineRegister").then((m) => m.DeadlineRegister), { loading: () => <RowsLoading label="Loading" /> });

const KINDS = [["all", "All dates"], ["hearing", "Hearings"], ["limitation", "Limitation"], ["filing", "Filings"], ["other", "Other"]] as const;

function AdvocateCalendar() {
  const [events, setEvents] = useState<CalendarEvent[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [kind, setKind] = useState<string>("all");
  const [failure, setFailure] = useState("");
  const { reloadDue } = usePro();
  const load = useCallback(() => {
    setFailed(false);
    calendarAcrossCases().then((response) => setEvents(response.events)).catch(() => setFailed(true));
  }, []);
  useEffect(load, [load]);
  const toggle = async (event: CalendarEvent) => {
    setFailure("");
    try { await updateCalendarEvent(event.case_id, event.id, { completed: !event.completed }); load(); reloadDue(); }
    catch { setFailure("That date could not be changed. Try again."); }
  };
  const groups = useMemo(() => {
    const rows = sortEvents((events ?? []).filter((event) => kind === "all" || event.kind === kind));
    return [
      { key: "overdue", title: "Overdue", rows: rows.filter((event) => event.state === "overdue") },
      { key: "soon", title: "Today and soon", rows: rows.filter((event) => event.state === "due_today" || event.state === "due_soon") },
      { key: "later", title: "Later", rows: rows.filter((event) => event.state === "upcoming") },
      { key: "done", title: "Done", rows: rows.filter((event) => event.state === "done") },
    ].filter((group) => group.rows.length);
  }, [events, kind]);
  if (failed) return <ErrorState title="Your dates could not be read." onRetry={load} />;
  if (!events) return <RowsLoading label="Reading your dates" rows={5} />;
  if (!events.length) {
    return (
      <EmptyState icon={CalendarPlus} title="No dates yet" action={<ProLink to={{ section: "cases" }} className="pro-button">Open a case to add one</ProLink>}>
        Add a hearing or a limitation date inside a case, and it appears here with every other case&apos;s.
      </EmptyState>
    );
  }
  return (
    <div className="pro-stack">
      <div className="pro-segment" role="group" aria-label="Which dates to show">
        {KINDS.map(([value, label]) => <button key={value} type="button" aria-pressed={kind === value} onClick={() => setKind(value)}>{label}</button>)}
      </div>
      {failure && <p className="pro-form-error" role="alert">{failure}</p>}
      {!groups.length && <p className="pro-quiet">No date of this kind.</p>}
      {groups.map((group) => (
        <section key={group.key} className="pro-card" aria-label={group.title}>
          <div className="pro-card-head"><h2>{group.title}</h2><span className="pro-count-chip">{group.rows.length}</span></div>
          <ul className="pro-rows">
            {group.rows.map((event) => {
              const meta = eventStateMeta(event.state);
              return (
                <li key={event.id} className={`pro-date-row ${event.completed ? "is-done" : ""}`}>
                  <span className="pro-date-when"><strong>{formatDate(event.due_on)}</strong>{!event.completed && <small>{dayPhrase(event.days_from_today)}</small>}</span>
                  <span className="pro-due-main">
                    <strong>{event.title}</strong>
                    <span className="pro-meta">
                      <ProLink to={{ section: "case", caseId: event.case_id, tab: "dates" }} className="pro-meta-case">{event.case_title ?? "Open the case"}</ProLink>
                      <span className="capitalize">{event.kind}</span>
                    </span>
                  </span>
                  <span className={`pro-pill tone-${meta.tone}`}>{meta.label}</span>
                  <button type="button" className="icon-button" onClick={() => void toggle(event)} aria-label={event.completed ? `Reopen ${event.title}` : `Mark ${event.title} done`} title={event.completed ? "Reopen" : "Mark done"}>
                    {event.completed ? <RotateCcw size={15} /> : <Check size={15} />}
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}

export default function DeadlinesScreen() {
  const { isPolice, cases, navigate } = usePro();
  const options = useMemo(() => cases.map((item) => ({ id: item.id, title: item.title })), [cases]);
  return (
    <div className="pro-page">
      {isPolice ? (
        <>
          <PageHead title="Deadlines" lead="Every statutory limit across your open investigations, most urgent first. Overdue means no completion is recorded. Breached means the record shows it was late. A limit that cannot be computed says so." />
          <DeadlineRegister cases={options} onOpenCase={(caseId) => navigate({ section: "case", caseId, tab: "deadlines" })} />
        </>
      ) : (
        <>
          <PageHead title="Calendar" lead="Every hearing, limitation and filing date across your cases, most urgent first. Check each date against the file: a wrong one can lose a case." />
          <AdvocateCalendar />
        </>
      )}
    </div>
  );
}
