"use client";

import { RefreshCw } from "lucide-react";
import { getAdminOverview } from "@/lib/api";
import { formatCount, formatDuration, formatWhen } from "@/lib/admin-presentation";
import { getSystemHealth } from "@/lib/api-admin";
import { LoadState, Notice, PanelHeading, Stat, StatusPill, useLoaded } from "./shared";

export default function OverviewPanel() {
  const overview = useLoaded(getAdminOverview, "overview");
  const health = useLoaded(getSystemHealth, "health");
  const system = health.data;

  return (
    <div className="admin-stack">
      <section className="admin-panel">
        <PanelHeading title="At a glance" />
        <LoadState loading={overview.loading && !overview.data} error={overview.error} onRetry={overview.reload} />
        {overview.data && (
          <div className="admin-stats">
            <Stat label="Accounts" value={formatCount(overview.data.users_total)} />
            <Stat label="Active police" value={formatCount(overview.data.police_active)} />
            <Stat label="Active advocates" value={formatCount(overview.data.advocates_active)} />
            <Stat label="Awaiting validation" value={formatCount(overview.data.staged_intakes)} />
            <Stat label="Published additions" value={formatCount(overview.data.published_intakes)} />
            <Stat label="Audit rows" value={formatCount(overview.data.audit_events)} />
          </div>
        )}
      </section>

      <section className="admin-panel">
        <PanelHeading
          title="System health"
          description="Checked now, each dependency with a three second limit."
          actions={
            <button className="button-secondary admin-compact" onClick={health.reload} disabled={health.loading}>
              <RefreshCw size={13} className={health.loading ? "animate-spin" : undefined} aria-hidden="true" /> Check again
            </button>
          }
        />
        <LoadState loading={health.loading && !system} error={health.error} onRetry={health.reload} />
        {system && (
          <>
            <Notice tone={system.ready ? "ok" : "bad"}>
              {system.ready ? "Every dependency answered. The service can take requests." : "A dependency is unavailable. Requests that need it will fail."}
            </Notice>
            <ul className="admin-list">
              {Object.entries(system.report.dependencies).map(([name, dependency]) => (
                <li key={name} className="admin-doc-head">
                  <div>
                    <strong className="admin-capitalize">{name}</strong>
                    <small className="admin-muted admin-wrap"> {formatDuration(dependency.duration_ms)}{dependency.error_type ? ` / ${dependency.error_type}` : ""}{dependency.model ? ` / ${String(dependency.model)}` : ""}</small>
                  </div>
                  <StatusPill tone={dependency.status === "ready" ? "ok" : "bad"}>{dependency.status === "ready" ? "Ready" : "Unavailable"}</StatusPill>
                </li>
              ))}
            </ul>
            <dl className="admin-defs">
              <div><dt>Environment</dt><dd>{system.environment}</dd></div>
              <div><dt>Serving collection</dt><dd><code>{system.serving_collection}</code></dd></div>
              <div><dt>Database schema</dt><dd><code>{system.schema_revision ?? "Unknown"}</code></dd></div>
              <div><dt>Inference</dt><dd>{Object.entries(system.report.inference).map(([key, value]) => `${key}: ${value}`).join(", ") || "Unknown"}</dd></div>
              <div><dt>Job worker</dt><dd>{system.job_worker_enabled ? "Running in this process" : "Disabled"}</dd></div>
              <div><dt>Quarantined documents</dt><dd>{formatCount(system.quarantined_documents)}</dd></div>
            </dl>
          </>
        )}
      </section>

      {system && (
        <section className="admin-panel">
          <PanelHeading title="Job queue" description="Metadata only. Jobs hold what somebody asked, so payloads and results are not shown." />
          <div className="admin-stats">
            {["queued", "running", "succeeded", "failed", "cancelled"].map(name => (
              <Stat key={name} label={`${name[0].toUpperCase()}${name.slice(1)}`} value={formatCount(system.jobs.by_status[name] ?? 0)} />
            ))}
            <Stat label="Oldest waiting" value={system.jobs.oldest_queued_at ? formatWhen(system.jobs.oldest_queued_at) : "None"} />
          </div>
          {system.jobs.recent.length > 0 && (
            <details className="admin-details">
              <summary>Most recent jobs</summary>
              <div className="admin-table-scroll">
                <table className="admin-table">
                  <thead><tr><th scope="col">Type</th><th scope="col">Status</th><th scope="col">Progress</th><th scope="col">Attempts</th><th scope="col">Error</th><th scope="col">Created</th></tr></thead>
                  <tbody>
                    {system.jobs.recent.map(job => (
                      <tr key={job.id}>
                        <td>{job.type.replace(/_/g, " ")}</td>
                        <td>{job.status}</td>
                        <td>{job.progress}%</td>
                        <td>{job.attempts}</td>
                        <td>{job.error_code ?? ""}</td>
                        <td>{formatWhen(job.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          )}
        </section>
      )}
    </div>
  );
}
