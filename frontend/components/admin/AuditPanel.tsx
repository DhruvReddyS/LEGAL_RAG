"use client";

import { Search } from "lucide-react";
import { useEffect, useState } from "react";
import { formatWhen, metadataRows, toQuery } from "@/lib/admin-presentation";
import { getConsoleAudit } from "@/lib/api-admin";
import { LoadState, PanelHeading, Pager, useLoaded } from "./shared";

const PAGE_SIZE = 50;

/** A date input gives midnight local time; "until" should include that day. */
function dayBoundary(value: string, end: boolean): string {
  if (!value) return "";
  const date = new Date(`${value}T${end ? "23:59:59" : "00:00:00"}`);
  return Number.isNaN(date.getTime()) ? "" : date.toISOString();
}

export default function AuditPanel() {
  const [action, setAction] = useState("");
  const [resourceType, setResourceType] = useState("");
  const [actorInput, setActorInput] = useState("");
  const [actor, setActor] = useState("");
  const [resourceInput, setResourceInput] = useState("");
  const [resourceId, setResourceId] = useState("");
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");
  const [page, setPage] = useState(1);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setActor(actorInput.trim());
      const candidate = resourceInput.trim();
      setResourceId(/^[0-9a-f-]{36}$/i.test(candidate) ? candidate : "");
      setPage(1);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [actorInput, resourceInput]);

  const filters = {
    action,
    actor,
    resource_type: resourceType,
    resource_id: resourceId,
    since: dayBoundary(since, false),
    until: dayBoundary(until, true),
    page,
    page_size: PAGE_SIZE,
  };
  const { data, error, loading, reload } = useLoaded(() => getConsoleAudit(filters), toQuery(filters));
  const onChange = (setter: (value: string) => void) => (event: { target: { value: string } }) => {
    setter(event.target.value);
    setPage(1);
  };
  const hasFilters = Boolean(action || actorInput || resourceType || resourceInput || since || until);

  return (
    <section className="admin-panel">
      <PanelHeading title="Audit log" description="Who did what, and when. Rows record identifiers and counts. Any user or evidence text in older rows is removed before it reaches this page." />
      <div className="admin-filters">
        <label className="admin-inline-field">
          <span>Action</span>
          <select className="field" value={action} onChange={onChange(setAction)}>
            <option value="">All</option>
            {data?.actions.map(name => <option key={name} value={name}>{name}</option>)}
          </select>
        </label>
        <label className="admin-inline-field">
          <span>Resource</span>
          <select className="field" value={resourceType} onChange={onChange(setResourceType)}>
            <option value="">All</option>
            {data?.resource_types.map(name => <option key={name} value={name}>{name}</option>)}
          </select>
        </label>
        <label className="admin-search">
          <Search size={15} aria-hidden="true" />
          <span className="sr-only">Actor name or email</span>
          <input value={actorInput} placeholder="Actor name or email" onChange={event => setActorInput(event.target.value)} />
        </label>
        <label className="admin-search">
          <Search size={15} aria-hidden="true" />
          <span className="sr-only">Resource id</span>
          <input value={resourceInput} placeholder="Resource id" onChange={event => setResourceInput(event.target.value)} />
        </label>
        <label className="admin-inline-field">
          <span>From</span>
          <input className="field" type="date" value={since} onChange={onChange(setSince)} />
        </label>
        <label className="admin-inline-field">
          <span>To</span>
          <input className="field" type="date" value={until} onChange={onChange(setUntil)} />
        </label>
        {hasFilters && (
          <button
            className="admin-link"
            onClick={() => { setAction(""); setActorInput(""); setResourceType(""); setResourceInput(""); setSince(""); setUntil(""); setPage(1); }}
          >
            Clear filters
          </button>
        )}
      </div>
      <LoadState loading={loading && !data} error={error} onRetry={reload} empty={data && data.events.length === 0 ? "No audit rows match." : null} />
      {data && data.events.length > 0 && (
        <>
          <ul className="admin-list">
            {data.events.map(event => {
              const rows = metadataRows(event.metadata);
              return (
                <li key={event.id}>
                  <div className="admin-doc-head">
                    <code>{event.action}</code>
                    <time className="admin-muted" dateTime={event.timestamp}>{formatWhen(event.timestamp)}</time>
                  </div>
                  <small className="admin-muted admin-wrap">
                    {event.actor_name ? `${event.actor_name} (${event.actor_email})` : "System or removed account"} / {event.resource_type}{event.resource_id ? ` ${event.resource_id}` : ""}
                  </small>
                  {rows.length > 0 && (
                    <details className="admin-details">
                      <summary>Details</summary>
                      <dl className="admin-defs">
                        {rows.map(([key, value]) => <div key={key}><dt>{key}</dt><dd className="admin-wrap">{value}</dd></div>)}
                      </dl>
                    </details>
                  )}
                </li>
              );
            })}
          </ul>
          <Pager page={page} pageSize={PAGE_SIZE} total={data.total} onPage={setPage} noun="rows" />
        </>
      )}
    </section>
  );
}
