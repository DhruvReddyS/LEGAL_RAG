"use client";

import { Loader2, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ApiError } from "@/lib/api";
import { acceptConsent, changePassword, getAccountStatus, getPrivacyConfiguration } from "@/lib/api-platform";
import { SITE_ROUTES } from "@/lib/site";
import type { AccountStatus, PrivacyConfiguration } from "@/lib/types-platform";
import { useDialogFocus } from "@/components/useDialogFocus";

const message = (error: unknown, fallback: string) => (error instanceof ApiError ? error.message : fallback);

/** The full notice, as the running installation serves it. */
export function PrivacyNoticeBody({ config }: { config: PrivacyConfiguration }) {
  const { notice, grievance, data_fiduciary: fiduciary } = config;
  return (
    <div className="gate-notice" tabIndex={0} aria-label="Privacy notice">
      <h3>What is held</h3>
      <dl>
        {notice.personal_data.map(row => <div key={row.item}><dt>{row.item}</dt><dd>{row.detail}</dd></div>)}
      </dl>
      <h3>What it is used for</h3>
      <ul>{notice.purposes.map(line => <li key={line}>{line}</li>)}</ul>
      <h3>What does not happen</h3>
      <ul>{notice.what_does_not_happen.map(line => <li key={line}>{line}</li>)}</ul>
      <h3>Two exceptions</h3>
      <ul>{notice.known_exceptions.map(line => <li key={line}>{line}</li>)}</ul>
      <h3>Your choices</h3>
      <p>
        In Settings you can download your data, correct it, withdraw this consent as easily as you gave it, or erase your
        account. You can complain to the grievance officer of this installation and, if not satisfied, to the Data
        Protection Board.
      </p>
      <h3>Who answers for this installation</h3>
      <p>{fiduciary ?? "The operator has not named themselves."} {grievance.configured
        ? <>Grievance officer: {grievance.name}{grievance.email ? `, ${grievance.email}` : ""}{grievance.phone ? `, ${grievance.phone}` : ""}.</>
        : "No grievance officer has been named for this installation yet."}</p>
    </div>
  );
}

function ConsentDialog({ user, onAccepted, onSignOut }: { user: { name: string }; onAccepted: () => void; onSignOut: () => void }) {
  const [config, setConfig] = useState<PrivacyConfiguration | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const ref = useDialogFocus(true, () => undefined);

  useEffect(() => {
    getPrivacyConfiguration().then(setConfig).catch(() => setError("The notice could not be loaded. Check your connection and try again."));
  }, []);

  const accept = async () => {
    if (!config) return;
    setBusy(true);
    setError("");
    try {
      await acceptConsent(config.notice.version);
      onAccepted();
    } catch (failure) {
      setError(message(failure, "That could not be saved. Please try again."));
      setBusy(false);
    }
  };

  return (
    <div className="gate-backdrop">
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby="gate-title" className="gate-dialog">
        <div className="gate-heading"><ShieldCheck size={20} aria-hidden="true" /><h2 id="gate-title">Before you continue</h2></div>
        <p className="gate-lead">{user.name}, please read how your data is handled. Your account cannot be used until you accept, and you can withdraw at any time.</p>
        {config ? <PrivacyNoticeBody config={config} /> : !error && <p role="status" className="gate-lead"><Loader2 size={16} className="animate-spin inline" aria-hidden="true" /> Loading the notice&hellip;</p>}
        {error && <p role="alert" className="auth-error">{error}</p>}
        <p className="gate-small">Notice version {config?.notice.version ?? "—"}. <Link href={SITE_ROUTES.privacy} target="_blank" rel="noopener">Open the full notice</Link> · <Link href={SITE_ROUTES.terms} target="_blank" rel="noopener">Terms of use</Link></p>
        <div className="gate-actions">
          <button type="button" className="button-secondary" onClick={onSignOut}>Not now, sign out</button>
          <button type="button" className="button-primary" disabled={!config || busy} onClick={() => void accept()}>{busy ? "Saving…" : "I accept"}</button>
        </div>
      </div>
    </div>
  );
}

function ForcedPasswordDialog({ onChanged, onSignOut }: { onChanged: () => void; onSignOut: () => void }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const ref = useDialogFocus(true, () => undefined);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await changePassword(current, next);
      onChanged();
    } catch (failure) {
      setError(message(failure, "That could not be saved. Please try again."));
      setBusy(false);
    }
  };

  return (
    <div className="gate-backdrop">
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby="gate-pw-title" className="gate-dialog gate-narrow">
        <div className="gate-heading"><ShieldCheck size={20} aria-hidden="true" /><h2 id="gate-pw-title">Choose your own password</h2></div>
        <p className="gate-lead">Your administrator set the password you just used, so they know it. Replace it with one only you know.</p>
        <form className="auth-form" onSubmit={submit}>
          <label>Current password
            <input className="field" type="password" autoComplete="current-password" required value={current} onChange={event => setCurrent(event.target.value)} />
          </label>
          <label>New password, at least 12 characters
            <input className="field" type="password" autoComplete="new-password" required minLength={12} maxLength={72} value={next} onChange={event => setNext(event.target.value)} />
          </label>
          {error && <p role="alert" className="auth-error">{error}</p>}
          <div className="gate-actions">
            <button type="button" className="button-secondary" onClick={onSignOut}>Sign out</button>
            <button type="submit" className="button-primary" disabled={busy}>{busy ? "Saving…" : "Change password"}</button>
          </div>
        </form>
      </div>
    </div>
  );
}

/**
 * What must happen before the workspace can be used. A password an administrator
 * knows comes first: consent given under someone else's password is not worth
 * much. `onCleared` lets the page reload what the server refused until now.
 */
export default function AccountGate({ user, onCleared, onSignOut }: { user: { id: string; name: string }; onCleared: () => void; onSignOut: () => void }) {
  const [status, setStatus] = useState<AccountStatus | null>(null);

  const refresh = useCallback(() => {
    getAccountStatus().then(setStatus).catch(() => setStatus(null));
  }, []);
  useEffect(refresh, [refresh, user.id]);

  const cleared = () => {
    onCleared();
    refresh();
  };

  if (!status) return null;
  if (status.must_change_password) return <ForcedPasswordDialog onChanged={cleared} onSignOut={onSignOut} />;
  if (status.consent.required) return <ConsentDialog user={user} onAccepted={cleared} onSignOut={onSignOut} />;
  return null;
}
