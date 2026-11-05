"use client";

import { CalendarPlus, Check, Loader2, RotateCcw, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import {
  addCalendarEvent,
  calendarAcrossCases,
  caseCalendar,
  computeLimitation,
  deleteCalendarEvent,
  listLimitationArticles,
  updateCalendarEvent,
} from "@/lib/api-advocate";
import { dayPhrase, eventStateMeta, formatDate, groupArticles, sortEvents } from "@/lib/advocate-presentation";
import type { CalendarEvent, LimitationArticle, LimitationResult } from "@/lib/types-advocate";
import { Badge, Bullets, DateField, ErrorLine, errorText, NeedsCase, SourceList } from "./shared";

function EventRow({ event, onToggle, onDelete }: { event: CalendarEvent; onToggle?: () => void; onDelete?: () => void }) {
  const meta = eventStateMeta(event.state);
  const provision = typeof event.basis?.provision === "string" ? event.basis.provision : null;
  return (
    <li className={`adv-event ${event.state === "overdue" ? "is-overdue" : ""} ${event.completed ? "is-done" : ""}`}>
      <span className="adv-event-main">
        <strong>{event.title}</strong>
        <span className="adv-meta">
          {formatDate(event.due_on)}{event.completed ? "" : `, ${dayPhrase(event.days_from_today)}`}
          {event.case_title ? ` · ${event.case_title}` : ""}
          {provision ? ` · ${provision}` : ""}
        </span>
        {event.notes && <span className="adv-meta">{event.notes}</span>}
      </span>
      <Badge tone={meta.tone}>{meta.label}</Badge>
      {onToggle && (
        <button type="button" className="adv-icon-button" onClick={onToggle} aria-label={event.completed ? `Reopen ${event.title}` : `Mark ${event.title} done`} title={event.completed ? "Reopen" : "Mark done"}>
          {event.completed ? <RotateCcw size={14} /> : <Check size={14} />}
        </button>
      )}
      {onDelete && (
        <button type="button" className="adv-icon-button" onClick={onDelete} aria-label={`Delete ${event.title}`} title="Delete">
          <Trash2 size={14} />
        </button>
      )}
    </li>
  );
}

function LimitationCalculator({ caseId, onAdded }: { caseId: string; onAdded: () => void }) {
  const [articles, setArticles] = useState<LimitationArticle[]>([]);
  const [scopeNote, setScopeNote] = useState("");
  const [article, setArticle] = useState("");
  const [runsFrom, setRunsFrom] = useState("");
  const [excluded, setExcluded] = useState("");
  const [result, setResult] = useState<LimitationResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  const [added, setAdded] = useState(false);
  useEffect(() => {
    listLimitationArticles()
      .then((response) => { setArticles(response.articles); setScopeNote(response.scope_note); })
      .catch((error) => setFailure(errorText(error)));
  }, []);
  const chosen = articles.find((item) => item.key === article);
  const compute = async (addToCalendar: boolean) => {
    if (!article || !runsFrom) return;
    setBusy(true);
    setFailure("");
    try {
      const response = await computeLimitation(caseId, {
        article,
        runs_from: runsFrom,
        excluded_days: Number.parseInt(excluded, 10) || 0,
        add_to_calendar: addToCalendar,
      });
      setResult(response);
      setAdded(addToCalendar);
      if (addToCalendar) onAdded();
    } catch (error) {
      setFailure(errorText(error));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="adv-section">
      <h4 className="adv-heading">Limitation calculator</h4>
      <p className="adv-lede">{scopeNote} A wrong date can lose a case: check the article, the starting point and the exclusions yourself.</p>
      <form className="adv-form" onSubmit={(event) => { event.preventDefault(); void compute(false); }}>
        <div className="adv-grid">
          <label className="adv-label">Schedule article
            <select className="field" value={article} onChange={(event) => { setArticle(event.target.value); setResult(null); }}>
              <option value="">Choose</option>
              {groupArticles(articles).map(([division, items]) => (
                <optgroup key={division} label={division}>
                  {items.map((item) => <option key={item.key} value={item.key}>{item.article}: {item.description} ({item.period})</option>)}
                </optgroup>
              ))}
            </select>
            {chosen && <small>Runs from {chosen.runs_from}.</small>}
          </label>
          <DateField label="That date" value={runsFrom} onChange={(value) => { setRunsFrom(value); setResult(null); }} />
          <label className="adv-label">Days to exclude
            <input className="field" inputMode="numeric" value={excluded} placeholder="0" onChange={(event) => { setExcluded(event.target.value); setResult(null); }} />
            <small>For example, time to obtain a copy under s.12(2) and (3).</small>
          </label>
        </div>
        <div className="adv-actions">
          <button type="submit" className="button-primary" disabled={busy || !article || !runsFrom}>
            {busy && <Loader2 size={15} className="animate-spin" />}Compute
          </button>
        </div>
        <ErrorLine text={failure} />
      </form>
      {result && (
        <article className="adv-card">
          <div className="adv-card-head">
            <h4>Last day: {formatDate(result.last_day)}</h4>
            <button type="button" className="draft-action" disabled={added || busy} onClick={() => void compute(true)}>
              <CalendarPlus size={13} />{added ? "Added to calendar" : "Add to calendar"}
            </button>
          </div>
          {result.caution && <div className="adv-notice" role="note"><span>{result.caution}</span></div>}
          <Bullets title="How this was reached" items={result.steps} />
          <Bullets title="Not taken into account" items={result.not_applied} />
          <div><p className="adv-subhead">Provisions, as they read</p><SourceList sources={result.sources} /></div>
        </article>
      )}
    </section>
  );
}

export default function CalendarTool({ caseId, caseTitle, showAcross = true }: { caseId: string; caseTitle?: string; showAcross?: boolean }) {
  const [events, setEvents] = useState<CalendarEvent[] | null>(null);
  const [across, setAcross] = useState<CalendarEvent[] | null>(null);
  const [kind, setKind] = useState("hearing");
  const [title, setTitle] = useState("");
  const [dueOn, setDueOn] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  const refresh = useCallback(async () => {
    try {
      const everywhere = await calendarAcrossCases();
      setAcross(everywhere.events);
      if (caseId) setEvents((await caseCalendar(caseId)).events);
    } catch (error) {
      setFailure(errorText(error));
    }
  }, [caseId]);
  useEffect(() => { void refresh(); }, [refresh]);
  const add = async () => {
    if (title.trim().length < 2 || !dueOn) return;
    setBusy(true);
    setFailure("");
    try {
      await addCalendarEvent(caseId, { kind, title: title.trim(), due_on: dueOn, notes: notes.trim() || undefined });
      setTitle(""); setDueOn(""); setNotes("");
      await refresh();
    } catch (error) {
      setFailure(errorText(error));
    } finally {
      setBusy(false);
    }
  };
  const act = async (work: Promise<unknown>) => {
    setFailure("");
    try { await work; await refresh(); } catch (error) { setFailure(errorText(error)); }
  };
  return (
    <div className="adv-section">
      {showAcross && (
      <section className="adv-section">
        <h4 className="adv-heading">All my cases</h4>
        {across === null ? (
          <p className="adv-meta">Reading your dates…</p>
        ) : across.length ? (
          <ul className="adv-list">{sortEvents(across).slice(0, 8).map((event) => <EventRow key={event.id} event={event} />)}</ul>
        ) : (
          <p className="case-empty">No open dates in any of your cases.</p>
        )}
      </section>
      )}
      {!caseId ? <NeedsCase /> : (
        <>
          <section className="adv-section">
            <h4 className="adv-heading">{caseTitle ? `Dates in ${caseTitle}` : "Dates in this case"}</h4>
            {events && (events.length ? (
              <ul className="adv-list">
                {sortEvents(events).map((event) => (
                  <EventRow
                    key={event.id}
                    event={event}
                    onToggle={() => void act(updateCalendarEvent(caseId, event.id, { completed: !event.completed }))}
                    onDelete={() => void act(deleteCalendarEvent(caseId, event.id))}
                  />
                ))}
              </ul>
            ) : <p className="case-empty">No date recorded for this case.</p>)}
            <form className="adv-form" onSubmit={(event) => { event.preventDefault(); void add(); }}>
              <div className="adv-grid">
                <label className="adv-label">Kind
                  <select className="field" value={kind} onChange={(event) => setKind(event.target.value)}>
                    <option value="hearing">Hearing</option>
                    <option value="limitation">Limitation</option>
                    <option value="filing">Filing</option>
                    <option value="other">Other</option>
                  </select>
                </label>
                <label className="adv-label">What
                  <input className="field" value={title} maxLength={255} onChange={(event) => setTitle(event.target.value)} placeholder="Arguments on bail" />
                </label>
                <DateField label="Date" value={dueOn} onChange={setDueOn} />
                <label className="adv-label">Note (optional)
                  <input className="field" value={notes} maxLength={4000} onChange={(event) => setNotes(event.target.value)} />
                </label>
              </div>
              <div className="adv-actions">
                <button type="submit" className="button-primary" disabled={busy || title.trim().length < 2 || !dueOn}>
                  {busy ? <Loader2 size={15} className="animate-spin" /> : <CalendarPlus size={15} />}Add date
                </button>
              </div>
            </form>
          </section>
          <LimitationCalculator caseId={caseId} onAdded={() => void refresh()} />
        </>
      )}
      <ErrorLine text={failure} />
    </div>
  );
}
