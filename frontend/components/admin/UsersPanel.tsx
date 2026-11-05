"use client";

import { KeyRound, Loader2, LogOut, Search, Shield, ShieldCheck, ShieldOff, UserPlus } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { createAdminUser } from "@/lib/api";
import { clearResetText, formatWhen, resetDoneText, toQuery } from "@/lib/admin-presentation";
import {
  changeUserRole,
  listConsoleUsers,
  reactivateUser,
  revokeUserSessions,
  setForcePasswordReset,
  setMfaRequired,
  suspendUser,
} from "@/lib/api-admin";
import { rolePluralLabel } from "@/lib/admin-presentation";
import type { ConsoleUser } from "@/lib/types-admin";
import { ConfirmDialog, LoadState, messageOf, Notice, PanelHeading, Pager, Stat, StatusPill, useLoaded } from "./shared";

const PAGE_SIZE = 20;
const ROLES = ["citizen", "police", "advocate"] as const;

type Pending =
  | { kind: "suspend"; user: ConsoleUser }
  | { kind: "reactivate"; user: ConsoleUser }
  | { kind: "revoke"; user: ConsoleUser }
  | { kind: "reset"; user: ConsoleUser }
  | { kind: "role"; user: ConsoleUser; role: string };

export default function UsersPanel() {
  const [input, setInput] = useState("");
  const [q, setQ] = useState("");
  const [role, setRole] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [pending, setPending] = useState<Pending | null>(null);
  const [notice, setNotice] = useState<{ tone: "ok" | "bad"; text: string } | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => { setQ(input.trim()); setPage(1); }, 250);
    return () => window.clearTimeout(timer);
  }, [input]);

  const filters = { q, role, status, page, page_size: PAGE_SIZE };
  const { data, error, loading, reload } = useLoaded(() => listConsoleUsers(filters), toQuery(filters));

  const toggleMfa = async (user: ConsoleUser) => {
    setNotice(null);
    try {
      await setMfaRequired(user.id, !user.mfa_required);
      setNotice({ tone: "ok", text: `MFA is ${user.mfa_required ? "no longer required" : "now required"} for ${user.name}.` });
      reload();
    } catch (cause) { setNotice({ tone: "bad", text: messageOf(cause, "That was not saved.") }); }
  };

  return (
    <div className="admin-stack">
      <section className="admin-panel">
        <PanelHeading title="Users" description="Every account, citizens included. Each change here is audited, and a suspension or reset ends sessions at once." />
        {data && (
          <div className="admin-stats">
            {["citizen", "police", "advocate", "admin"].map(name => <Stat key={name} label={rolePluralLabel(name)} value={(data.by_role[name] ?? 0).toLocaleString("en-IN")} />)}
          </div>
        )}
        <div className="admin-filters">
          <label className="admin-search">
            <Search size={15} aria-hidden="true" />
            <span className="sr-only">Search by name or email</span>
            <input value={input} placeholder="Name or email" onChange={event => setInput(event.target.value)} />
          </label>
          <label className="admin-inline-field">
            <span>Role</span>
            <select className="field" value={role} onChange={event => { setRole(event.target.value); setPage(1); }}>
              <option value="">All</option>
              {[...ROLES, "admin"].map(name => <option key={name} value={name}>{name}</option>)}
            </select>
          </label>
          <label className="admin-inline-field">
            <span>Status</span>
            <select className="field" value={status} onChange={event => { setStatus(event.target.value); setPage(1); }}>
              <option value="">All</option>
              <option value="active">Active</option>
              <option value="suspended">Suspended</option>
            </select>
          </label>
        </div>
        {notice && <Notice tone={notice.tone}>{notice.text}</Notice>}
        <LoadState loading={loading && !data} error={error} onRetry={reload} empty={data && data.users.length === 0 ? "No accounts match." : null} />
        {data && data.users.length > 0 && (
          <>
            <ul className="admin-list">
              {data.users.map(user => (
                <li key={user.id}>
                  <div className="admin-doc-head">
                    <div className="admin-user">
                      <strong>{user.name}</strong>
                      <span className="admin-muted admin-wrap">{user.email}</span>
                    </div>
                    <div className="admin-row">
                      <StatusPill tone="neutral">{user.role}</StatusPill>
                      <StatusPill tone={user.is_active ? "ok" : "bad"}>{user.is_active ? "Active" : "Suspended"}</StatusPill>
                      {user.force_password_reset && <StatusPill tone="warn">Reset required</StatusPill>}
                      {user.first_password_change_pending && <StatusPill tone="warn">First password not changed</StatusPill>}
                      {user.mfa_required && <StatusPill tone="warn">MFA required</StatusPill>}
                    </div>
                  </div>
                  <small className="admin-muted admin-wrap">
                    {user.case_count} cases / joined {formatWhen(user.created_at)} / last sign-in {formatWhen(user.last_login_at)}
                  </small>
                  {user.suspended_reason && <p className="admin-note">Suspended: {user.suspended_reason}</p>}
                  {user.manageable ? (
                    <div className="admin-actions">
                      {user.is_active ? (
                        <button className="button-secondary admin-compact" onClick={() => setPending({ kind: "suspend", user })}><ShieldOff size={13} aria-hidden="true" /> Suspend</button>
                      ) : (
                        <button className="button-secondary admin-compact" onClick={() => setPending({ kind: "reactivate", user })}><Shield size={13} aria-hidden="true" /> Reactivate</button>
                      )}
                      <button className="button-secondary admin-compact" onClick={() => setPending({ kind: "reset", user })}><KeyRound size={13} aria-hidden="true" /> {user.force_password_reset ? "Clear reset" : "Force reset"}</button>
                      <button className="button-secondary admin-compact" onClick={() => setPending({ kind: "revoke", user })}><LogOut size={13} aria-hidden="true" /> End sessions</button>
                      <button className="button-secondary admin-compact" aria-pressed={user.mfa_required} onClick={() => toggleMfa(user)}><ShieldCheck size={13} aria-hidden="true" /> {user.mfa_required ? "Stop requiring MFA" : "Require MFA"}</button>
                      <label className="admin-inline-field">
                        <span className="sr-only">Change role for {user.name}</span>
                        <select
                          className="field admin-compact-select"
                          value={user.role}
                          disabled={user.case_count > 0}
                          title={user.case_count > 0 ? "Role cannot change while the account owns cases" : undefined}
                          onChange={event => setPending({ kind: "role", user, role: event.target.value })}
                        >
                          {ROLES.map(name => <option key={name} value={name}>{name}</option>)}
                        </select>
                      </label>
                    </div>
                  ) : (
                    <small className="admin-muted">Administrator accounts are not managed here.</small>
                  )}
                </li>
              ))}
            </ul>
            <Pager page={page} pageSize={PAGE_SIZE} total={data.total} onPage={setPage} noun="accounts" />
          </>
        )}
      </section>

      <ProvisionForm onCreated={reload} />

      {pending?.kind === "suspend" && (
        <ConfirmDialog
          title={`Suspend ${pending.user.name}`}
          confirmLabel="Suspend"
          danger
          requireReason
          minReason={5}
          reasonLabel="Why"
          body={<p>They are signed out everywhere at once and cannot sign in. Their data stays as it is.</p>}
          onClose={() => setPending(null)}
          onConfirm={async reason => { await suspendUser(pending.user.id, reason); setNotice({ tone: "ok", text: `${pending.user.name} is suspended.` }); reload(); }}
        />
      )}
      {pending?.kind === "reactivate" && (
        <ConfirmDialog
          title={`Reactivate ${pending.user.name}`}
          confirmLabel="Reactivate"
          body={<p>They can sign in again.</p>}
          onClose={() => setPending(null)}
          onConfirm={async () => { await reactivateUser(pending.user.id); setNotice({ tone: "ok", text: `${pending.user.name} is active.` }); reload(); }}
        />
      )}
      {pending?.kind === "revoke" && (
        <ConfirmDialog
          title={`End ${pending.user.name}'s sessions`}
          confirmLabel="End sessions"
          body={<p>They are signed out on every device and can sign in again straight away.</p>}
          onClose={() => setPending(null)}
          onConfirm={async () => { await revokeUserSessions(pending.user.id); setNotice({ tone: "ok", text: `${pending.user.name}'s sessions have ended.` }); reload(); }}
        />
      )}
      {pending?.kind === "reset" && (
        <ConfirmDialog
          title={pending.user.force_password_reset ? "Clear the required reset" : `Force a password reset for ${pending.user.name}`}
          confirmLabel={pending.user.force_password_reset ? "Clear it" : "Require a reset"}
          body={<p>{clearResetText(pending.user)}</p>}
          onClose={() => setPending(null)}
          onConfirm={async () => { await setForcePasswordReset(pending.user.id, !pending.user.force_password_reset); setNotice({ tone: "ok", text: resetDoneText(pending.user) }); reload(); }}
        />
      )}
      {pending?.kind === "role" && (
        <ConfirmDialog
          title={`Change ${pending.user.name}'s role`}
          confirmLabel={`Make ${pending.role}`}
          body={<p>From {pending.user.role} to {pending.role}. They are signed out everywhere and their new access starts at their next sign-in.</p>}
          onClose={() => setPending(null)}
          onConfirm={async () => { await changeUserRole(pending.user.id, pending.role); setNotice({ tone: "ok", text: `${pending.user.name} is now ${pending.role}.` }); reload(); }}
        />
      )}
    </div>
  );
}

function ProvisionForm({ onCreated }: { onCreated: () => void }) {
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ tone: "ok" | "bad"; text: string } | null>(null);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const element = event.currentTarget;
    const form = new FormData(element);
    setBusy(true);
    setNotice(null);
    try {
      await createAdminUser({
        name: String(form.get("name")),
        email: String(form.get("email")),
        password: String(form.get("password")),
        role: String(form.get("role")) as "police" | "advocate",
      });
      element.reset();
      setNotice({ tone: "ok", text: "Professional account created." });
      onCreated();
    } catch (cause) { setNotice({ tone: "bad", text: messageOf(cause, "Account creation failed") }); }
    finally { setBusy(false); }
  };
  return (
    <section className="admin-panel">
      <PanelHeading title="Provision a professional account" description="Police and advocate accounts cannot self-register." />
      <form className="admin-form" onSubmit={submit}>
        <div className="admin-form-pair">
          <label className="admin-field"><span>Full name</span><input required name="name" minLength={2} className="field" autoComplete="off" /></label>
          <label className="admin-field"><span>Work email</span><input required name="email" type="email" className="field" autoComplete="off" /></label>
        </div>
        <div className="admin-form-pair">
          <label className="admin-field"><span>Role</span><select name="role" className="field"><option value="police">Police</option><option value="advocate">Advocate</option></select></label>
          <label className="admin-field"><span>Temporary password</span><input required name="password" type="password" minLength={12} className="field" autoComplete="new-password" /></label>
        </div>
        <div className="admin-actions">
          <button disabled={busy} className="button-primary">
            {busy ? <Loader2 size={14} className="animate-spin" aria-hidden="true" /> : <UserPlus size={14} aria-hidden="true" />} Create account
          </button>
        </div>
        {notice && <Notice tone={notice.tone}>{notice.text}</Notice>}
      </form>
    </section>
  );
}
