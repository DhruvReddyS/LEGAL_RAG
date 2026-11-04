"use client";

import { Eraser, Loader2, ScanSearch } from "lucide-react";
import { useEffect, useState } from "react";
import {
  dryRunIsExpired,
  formatCount,
  formatWhen,
  RETENTION_COUNT_LABELS,
  retentionError,
  totalToPurge,
} from "@/lib/admin-presentation";
import { getRetention, runRetentionDryRun, runRetentionPurge, setRetentionPolicy } from "@/lib/api-admin";
import type { RetentionCategory, RetentionDryRun } from "@/lib/types-admin";
import { ConfirmDialog, LoadState, messageOf, Notice, PanelHeading, StatusPill, useLoaded } from "./shared";

export default function RetentionPanel() {
  const { data, error, loading, reload } = useLoaded(getRetention, "retention");
  const [preview, setPreview] = useState<RetentionDryRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [notice, setNotice] = useState<{ tone: "ok" | "warn" | "bad"; text: string } | null>(null);

  if (!data) return <LoadState loading={loading} error={error} onRetry={reload} />;

  const expired = preview ? dryRunIsExpired(preview.expires_at) : false;

  const runDry = async () => {
    setBusy(true);
    setNotice(null);
    try {
      setPreview(await runRetentionDryRun());
      reload();
    } catch (cause) { setNotice({ tone: "bad", text: messageOf(cause, "The dry run failed.") }); }
    finally { setBusy(false); }
  };

  return (
    <div className="admin-stack">
      <section className="admin-panel">
        <PanelHeading
          title="Retention periods"
          description="Everything is kept until you set a period. Blank means keep. A purge only ever deletes what a dry run has shown you."
        />
        <ul className="admin-list">
          {data.categories.map(category => (
            <PolicyRow
              key={category.key}
              category={category}
              onSaved={() => { setPreview(null); reload(); }}
            />
          ))}
        </ul>
      </section>

      <section className="admin-panel">
        <PanelHeading
          title="Purge"
          description={`Run a dry run, read it, then purge within ${data.dry_run_valid_minutes} minutes. Changing a period cancels the dry run.`}
          actions={
            <button className="button-secondary" disabled={busy} onClick={runDry}>
              {busy ? <Loader2 size={14} className="animate-spin" aria-hidden="true" /> : <ScanSearch size={14} aria-hidden="true" />} Dry run
            </button>
          }
        />
        {notice && <Notice tone={notice.tone}>{notice.text}</Notice>}
        {preview && (
          <div className="admin-stack is-tight">
            <dl className="admin-defs">
              {Object.entries(preview.counts).map(([key, value]) => (
                <div key={key}>
                  <dt>{RETENTION_COUNT_LABELS[key] ?? key}</dt>
                  <dd>
                    {formatCount(value)}
                    {preview.cutoffs[key] ? <small className="admin-muted"> older than {formatWhen(preview.cutoffs[key])}</small> : null}
                  </dd>
                </div>
              ))}
            </dl>
            {expired ? (
              <Notice tone="warn">This dry run has expired. Run it again.</Notice>
            ) : totalToPurge(preview.counts) === 0 ? (
              <Notice tone="ok">Nothing is due for deletion.</Notice>
            ) : (
              <div className="admin-actions">
                <button className="button-primary admin-danger" onClick={() => setConfirming(true)}>
                  <Eraser size={14} aria-hidden="true" /> Purge {formatCount(totalToPurge(preview.counts))} records
                </button>
                <small className="admin-muted">Good until {formatWhen(preview.expires_at)}</small>
              </div>
            )}
          </div>
        )}
        {data.runs.length > 0 && (
          <details className="admin-details">
            <summary>Past runs</summary>
            <ul className="admin-list">
              {data.runs.map(run => (
                <li key={run.id}>
                  <div className="admin-row">
                    <StatusPill tone={run.kind === "purge" ? "warn" : "neutral"}>{run.kind === "purge" ? "Purge" : "Dry run"}</StatusPill>
                    <span className="admin-muted">{run.requested_by ?? "Former administrator"}, {formatWhen(run.created_at)}</span>
                  </div>
                  <small className="admin-muted admin-wrap">
                    {Object.entries(run.counts).map(([key, value]) => `${RETENTION_COUNT_LABELS[key] ?? key}: ${value}`).join(" / ") || "Nothing counted"}
                  </small>
                </li>
              ))}
            </ul>
          </details>
        )}
      </section>

      {confirming && preview && (
        <ConfirmDialog
          title="Purge permanently"
          confirmLabel="Purge"
          danger
          typed={preview.confirmation}
          body={<p>This cannot be undone. {formatCount(totalToPurge(preview.counts))} records go, exactly as the dry run listed. Closed cases are erased from object storage and the vector store as well as the database.</p>}
          onClose={() => setConfirming(false)}
          onConfirm={async () => {
            const result = await runRetentionPurge(preview.id, preview.confirmation);
            const failed = result.deleted.closed_cases_failed;
            setNotice(
              failed
                ? { tone: "warn", text: `Purge finished, but ${failed} closed cases could not be erased from every store. They were kept for the next run.` }
                : { tone: "ok", text: `Purged ${formatCount(totalToPurge(result.deleted))} records. This is in the audit log.` },
            );
            setPreview(null);
            reload();
          }}
        />
      )}
    </div>
  );
}

function PolicyRow({ category, onSaved }: { category: RetentionCategory; onSaved: () => void }) {
  const stored = category.days === null ? "" : String(category.days);
  const [value, setValue] = useState(stored);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => setValue(stored), [stored]);
  const invalid = retentionError(value, category.minimum_days);
  const id = `retention-${category.key}`;
  return (
    <li>
      <div className="admin-doc-head">
        <div>
          <strong>{category.label}</strong>
          <p className="admin-muted">{category.description}</p>
        </div>
        <StatusPill tone={category.days === null ? "neutral" : "warn"}>{category.days === null ? "Kept" : `${category.days} days`}</StatusPill>
      </div>
      <div className="admin-form-row admin-policy">
        <label className="admin-field" htmlFor={id}>
          <span>Days to keep, at least {category.minimum_days}</span>
          <input id={id} className="field" inputMode="numeric" value={value} placeholder="Keep" aria-invalid={Boolean(invalid)} onChange={event => setValue(event.target.value)} />
        </label>
        <button
          className="button-secondary"
          disabled={value === stored || Boolean(invalid) || busy}
          onClick={async () => {
            setBusy(true);
            setError("");
            try {
              await setRetentionPolicy(category.key, value.trim() === "" ? null : Number(value));
              onSaved();
            } catch (cause) { setError(messageOf(cause, "That was not saved.")); }
            finally { setBusy(false); }
          }}
        >
          Save
        </button>
      </div>
      {invalid && <small className="admin-error">{invalid}</small>}
      {error && <Notice tone="bad">{error}</Notice>}
    </li>
  );
}
