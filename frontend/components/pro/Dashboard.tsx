"use client";

import { ArrowRight, BookOpenText, CalendarClock, CheckCircle2, FileText, MessageSquare, Plus, Scale } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { getSupervisedUnit } from "@/lib/api-police";
import { sumCounts, supervisedUnits } from "@/lib/police-presentation";
import { countBuckets, needsAttention, nextDueByCase, plural, shortDate, sortDue, type DueItem } from "@/lib/pro-presentation";
import type { ProRoute } from "@/lib/pro-route";
import type { SupervisedUnit } from "@/lib/types-police";
import { Card, DueRow, ErrorState, PageHead, ProLink, RowsLoading, StatusPill, usePro } from "./context";

const today = () => new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric" });

export function dueTarget(item: DueItem, isPolice: boolean): ProRoute {
  return { section: "case", caseId: item.caseId, tab: isPolice ? "deadlines" : "dates" };
}

function Tile({ label, value, tone, to, hint }: { label: string; value: string | number; tone?: "bad" | "warn"; to: ProRoute; hint?: string }) {
  return (
    <ProLink to={to} className={`pro-tile ${tone && value ? `tone-${tone}` : ""}`}>
      <strong>{value}</strong>
      <span>{label}</span>
      {hint && <small>{hint}</small>}
    </ProLink>
  );
}

function FirstSteps() {
  const { isPolice, noun, openNewCase } = usePro();
  const steps = isPolice
    ? [
        { title: "Open your first investigation", body: "Give it a title. Everything you add stays inside it, and only you can read it." },
        { title: "Record the key dates", body: "Enter the dates of the FIR, the arrest or the seizure. Time limits are computed from those dates." },
        { title: "Add files and start the record", body: "Upload statements and reports, then keep exhibits, witnesses and drafts in the same place." },
      ]
    : [
        { title: "Open your first case", body: "Give it a title. Everything you add stays inside it, and only you can read it." },
        { title: "Add hearings and limitation dates", body: "They appear here and on your calendar, with what is overdue shown first." },
        { title: "Add client files and prepare", body: "Upload the papers, then work on strategy, authorities and drafts in the same place." },
      ];
  return (
    <section className="pro-first" aria-labelledby="first-steps">
      <h2 id="first-steps">Get started in three steps</h2>
      <ol>
        {steps.map((step, index) => (
          <li key={step.title}>
            <b aria-hidden="true">{index + 1}</b>
            <div><h3>{step.title}</h3><p>{step.body}</p></div>
          </li>
        ))}
      </ol>
      <div className="pro-first-actions">
        <button type="button" className="pro-button is-primary" onClick={openNewCase}><Plus size={15} aria-hidden="true" />New {noun}</button>
        <ProLink to={{ section: "research" }} className="pro-button">Ask a law question first</ProLink>
      </div>
    </section>
  );
}

function ActiveCases() {
  const { cases, due, nounPlural, isPolice, casesWithoutFacts, noun } = usePro();
  const next = useMemo(() => nextDueByCase(due), [due]);
  const open = useMemo(() => {
    const rows = cases.filter((item) => item.status === "open");
    return rows.sort((a, b) => {
      const [first, second] = [next.get(a.id), next.get(b.id)];
      if (first && second) return sortDue([first, second])[0] === first ? -1 : 1;
      return first ? -1 : second ? 1 : Date.parse(b.created_at) - Date.parse(a.created_at);
    }).slice(0, 5);
  }, [cases, next]);
  const nothing = new Set(casesWithoutFacts.map((item) => item.case_id));
  return (
    <Card title={`Active ${nounPlural.toLowerCase()}`} id="dash-active" action={<ProLink to={{ section: "cases" }} className="pro-card-link">See all<ArrowRight size={13} aria-hidden="true" /></ProLink>}>
      {open.length ? (
        <ul className="pro-rows">
          {open.map((item) => {
            const coming = next.get(item.id);
            return (
              <li key={item.id}>
                <ProLink to={{ section: "case", caseId: item.id }} className="pro-case-row">
                  <span className="pro-due-main">
                    <strong>{item.title}</strong>
                    <span className="pro-meta">
                      {coming
                        ? <span>Next: {coming.title}, {coming.when}</span>
                        : <span>{isPolice && nothing.has(item.id) ? "No dates recorded yet" : "Nothing due"}</span>}
                    </span>
                  </span>
                  <StatusPill status={item.status} />
                </ProLink>
              </li>
            );
          })}
        </ul>
      ) : <p className="pro-quiet">No {noun} is open at the moment.</p>}
    </Card>
  );
}

function RecentActivity() {
  const { chats, cases, openChat, noun } = usePro();
  const rows = useMemo(() => {
    const title = new Map(cases.map((item) => [item.id, item.title]));
    const asked = chats.map((chat) => ({ key: `chat-${chat.id}`, at: chat.updatedAt, label: chat.title, note: chat.caseId ? title.get(chat.caseId) ?? "A case" : "Law question", chat: chat.id, caseId: null as string | null }));
    const opened = cases.map((item) => ({ key: `case-${item.id}`, at: Date.parse(item.created_at) || 0, label: item.title, note: `Opened this ${noun}`, chat: null as string | null, caseId: item.id }));
    return [...asked, ...opened].sort((a, b) => b.at - a.at).slice(0, 6);
  }, [chats, cases, noun]);
  return (
    <Card title="Recent activity" id="dash-activity">
      {rows.length ? (
        <ul className="pro-rows">
          {rows.map((row) => (
            <li key={row.key}>
              {row.caseId
                ? <ProLink to={{ section: "case", caseId: row.caseId }} className="pro-activity"><span className="pro-due-main"><strong>{row.label}</strong><span className="pro-meta"><span>{row.note}</span></span></span><time>{shortDate(row.at)}</time></ProLink>
                : <button type="button" className="pro-activity" onClick={() => openChat(row.chat!)}><span className="pro-due-main"><strong>{row.label}</strong><span className="pro-meta"><span>{row.note}</span></span></span><time>{shortDate(row.at)}</time></button>}
            </li>
          ))}
        </ul>
      ) : <p className="pro-quiet">Questions you ask and {noun}s you open will show here.</p>}
    </Card>
  );
}

function QuickActions() {
  const { isPolice } = usePro();
  const actions: { to: ProRoute; label: string; icon: typeof Scale }[] = [
    { to: { section: "deadlines" }, label: isPolice ? "Open the deadline register" : "Open the calendar", icon: CalendarClock },
    { to: { section: "research" }, label: "Ask a law question", icon: MessageSquare },
    { to: { section: "law" }, label: "Look up a provision", icon: BookOpenText },
    { to: { section: "drafts" }, label: "See all drafts", icon: FileText },
  ];
  return (
    <Card title="Quick actions" id="dash-quick">
      <ul className="pro-actions">
        {actions.map((action) => (
          <li key={action.label}><ProLink to={action.to} className="pro-action"><action.icon size={15} aria-hidden="true" />{action.label}</ProLink></li>
        ))}
      </ul>
    </Card>
  );
}

/** Shown to a supervisor only. What the unit has overdue, and a way into it. */
function UnitCard() {
  const { units } = usePro();
  const supervised = useMemo(() => supervisedUnits(units), [units]);
  const unitId = supervised[0]?.unit_id;
  const [unit, setUnit] = useState<SupervisedUnit | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!unitId) return;
    let cancelled = false;
    getSupervisedUnit(unitId).then((data) => { if (!cancelled) setUnit(data); }).catch(() => { if (!cancelled) setFailed(true); });
    return () => { cancelled = true; };
  }, [unitId]);
  if (!unitId) return null;
  return (
    <Card title="Unit supervision" id="dash-unit" action={<ProLink to={{ section: "unit" }} className="pro-card-link">Open<ArrowRight size={13} aria-hidden="true" /></ProLink>}>
      {failed ? <p className="pro-quiet">The unit could not be read just now.</p> : !unit ? <RowsLoading label="Reading the unit" rows={1} /> : (
        <dl className="pro-facts">
          <div><dt>Unit</dt><dd>{unit.unit_name}</dd></div>
          <div><dt>Overdue or expiring</dt><dd>{sumCounts(unit.counts, ["overdue", "imminent"])}</dd></div>
          <div><dt>Breached on record</dt><dd>{unit.counts.breached ?? 0}</dd></div>
          <div><dt>Open cases</dt><dd>{unit.cases.length}</dd></div>
        </dl>
      )}
    </Card>
  );
}

function Attention() {
  const { due, dueState, reloadDue, isPolice, casesWithoutFacts } = usePro();
  const items = useMemo(() => needsAttention(due), [due]);
  const label = isPolice ? "Deadline register" : "Calendar";
  return (
    <Card title="Needs attention" id="dash-attention" action={<ProLink to={{ section: "deadlines" }} className="pro-card-link">{label}<ArrowRight size={13} aria-hidden="true" /></ProLink>}>
      {dueState === "loading" && <RowsLoading label="Reading what is due" />}
      {dueState === "failed" && <ErrorState title={isPolice ? "Your deadlines could not be read." : "Your dates could not be read."} onRetry={reloadDue} />}
      {dueState === "ready" && (items.length ? (
        <ul className="pro-rows">
          {items.slice(0, 7).map((item) => <DueRow key={item.id} item={item} to={dueTarget(item, isPolice)} />)}
          {items.length > 7 && <li className="pro-more"><ProLink to={{ section: "deadlines" }}>{plural(items.length - 7, "more item")}</ProLink></li>}
        </ul>
      ) : (
        <p className="pro-clear">
          <CheckCircle2 size={16} aria-hidden="true" />
          {isPolice
            ? (casesWithoutFacts.length
              ? "Nothing computed is overdue or expiring soon. That does not cover cases with no dates recorded."
              : "Nothing computed is overdue or expiring soon.")
            : "Nothing recorded is overdue or due soon."}
        </p>
      ))}
    </Card>
  );
}

function PoliceSide() {
  const { casesWithoutFacts } = usePro();
  if (!casesWithoutFacts.length) return null;
  return (
    <Card title="No dates recorded" id="dash-nofacts">
      <p className="pro-quiet">No time limit can be computed for these. That does not mean none applies.</p>
      <ul className="pro-rows">
        {casesWithoutFacts.slice(0, 5).map((item) => (
          <li key={item.case_id}>
            <ProLink to={{ section: "case", caseId: item.case_id, tab: "deadlines" }} className="pro-case-row">
              <span className="pro-due-main"><strong>{item.title}</strong></span>
              <span className="pro-card-link">Record dates<ArrowRight size={13} aria-hidden="true" /></span>
            </ProLink>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function AdvocateDates() {
  const { due, dueState } = usePro();
  const coming = useMemo(() => sortDue(due.filter((item) => item.bucket !== "done" && item.bucket !== "act_now")), [due]);
  const hearings = coming.filter((item) => item.tag === "Hearing").slice(0, 4);
  const limitation = coming.filter((item) => item.tag === "Limitation").slice(0, 4);
  if (dueState !== "ready") return null;
  return (
    <div className="pro-two">
      <Card title="Next hearings" id="dash-hearings">
        {hearings.length ? <ul className="pro-rows">{hearings.map((item) => <DueRow key={item.id} item={item} to={dueTarget(item, false)} />)}</ul> : <p className="pro-quiet">No hearing is recorded ahead.</p>}
      </Card>
      <Card title="Limitation dates" id="dash-limitation">
        {limitation.length ? <ul className="pro-rows">{limitation.map((item) => <DueRow key={item.id} item={item} to={dueTarget(item, false)} />)}</ul> : <p className="pro-quiet">No limitation date is recorded ahead.</p>}
      </Card>
    </div>
  );
}

export default function Dashboard() {
  const { isPolice, cases, casesState, reloadCases, due, dueState, noun, nounPlural, openNewCase } = usePro();
  const counts = useMemo(() => countBuckets(due), [due]);
  const openCount = cases.filter((item) => item.status === "open").length;
  const nextHearing = useMemo(() => sortDue(due.filter((item) => item.tag === "Hearing" && item.bucket !== "done" && item.bucket !== "act_now"))[0], [due]);
  const known = dueState === "ready";
  return (
    <div className="pro-page">
      <PageHead
        title="Dashboard"
        lead={today()}
        action={<button type="button" className="pro-button is-primary" onClick={openNewCase}><Plus size={15} aria-hidden="true" />New {noun}</button>}
      />
      {casesState === "failed" && <ErrorState title={`Your ${nounPlural.toLowerCase()} could not be read.`} onRetry={reloadCases} />}
      {casesState === "loading" && <RowsLoading label="Loading your dashboard" rows={5} />}
      {casesState === "ready" && !cases.length && (
        <>
          <FirstSteps />
          <div className="pro-two"><QuickActions /><RecentActivity /></div>
        </>
      )}
      {casesState === "ready" && cases.length > 0 && (
        <>
          <div className="pro-tiles" aria-label="At a glance">
            <Tile label="Overdue" value={known ? counts.act_now : "—"} tone="bad" to={{ section: "deadlines" }} />
            <Tile label="Due soon" value={known ? counts.soon : "—"} tone="warn" to={{ section: "deadlines" }} />
            {isPolice
              ? <Tile label="Breached on record" value={known ? counts.breached : "—"} tone="bad" to={{ section: "deadlines" }} />
              : <Tile label="Next hearing" value={nextHearing ? nextHearing.when : known ? "None" : "—"} to={{ section: "deadlines" }} />}
            <Tile label={`Open ${nounPlural.toLowerCase()}`} value={openCount} to={{ section: "cases" }} />
          </div>
          <div className="pro-dash">
            <div className="pro-dash-main">
              <Attention />
              {!isPolice && <AdvocateDates />}
              <ActiveCases />
            </div>
            <div className="pro-dash-side">
              {isPolice && <UnitCard />}
              {isPolice && <PoliceSide />}
              <QuickActions />
              <RecentActivity />
            </div>
          </div>
        </>
      )}
    </div>
  );
}

