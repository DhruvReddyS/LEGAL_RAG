"use client";

import { ArrowLeft } from "lucide-react";
import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api";
import { getPrivacyConfiguration, redeemResetCode, requestResetByMail } from "@/lib/api-platform";

/**
 * Getting back in. The path that always works is a one-time code from an
 * administrator: a self-hosted install cannot assume a mail relay, or that one
 * is reachable. Mail is offered only where the operator has configured it.
 */
export default function ForgotPassword({ initialEmail, onBack, onDone }: { initialEmail: string; onBack: () => void; onDone: (email: string) => void }) {
  const [email, setEmail] = useState(initialEmail);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [mailAvailable, setMailAvailable] = useState(false);

  useEffect(() => {
    getPrivacyConfiguration().then(config => setMailAvailable(config.self_service_reset)).catch(() => setMailAvailable(false));
  }, []);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await redeemResetCode(email.trim(), code.trim(), password);
      onDone(email.trim());
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "Unable to reach the workspace. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  const sendMail = async () => {
    setError("");
    setNote("");
    try {
      await requestResetByMail(email.trim());
      setNote("If that address has an account, a code is on its way. It works once.");
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "Unable to reach the workspace. Please try again.");
    }
  };

  return (
    <>
      <div className="auth-heading">
        <h2>Reset your password</h2>
        <span>
          {mailAvailable
            ? "Ask for a one-time code by email, or get one from your administrator."
            : "Ask your administrator for a one-time code, then enter it here. If you run this installation yourself, create a second administrator on the server."}
        </span>
      </div>
      <form className="auth-form" onSubmit={submit}>
        <label>Email address
          <input className="field" type="email" autoComplete="email" required value={email} onChange={event => setEmail(event.target.value)} />
        </label>
        {mailAvailable && <button type="button" className="auth-link" disabled={!email.trim()} onClick={() => void sendMail()}>Email me a code</button>}
        {note && <p role="status" className="acct-success">{note}</p>}
        <label>One-time code
          <input className="field" autoComplete="one-time-code" required minLength={8} value={code} onChange={event => setCode(event.target.value)} />
        </label>
        <label>New password, at least 12 characters
          <input className="field" type="password" autoComplete="new-password" required minLength={12} maxLength={72} value={password} onChange={event => setPassword(event.target.value)} />
        </label>
        {error && <p role="alert" className="auth-error">{error}</p>}
        <button type="submit" disabled={busy} className="auth-submit"><span>{busy ? "Saving…" : "Set new password"}</span></button>
      </form>
      <div className="auth-switch">
        <span>Remembered it?</span>
        <button type="button" onClick={onBack}><ArrowLeft size={13} aria-hidden="true" />Back to sign in</button>
      </div>
    </>
  );
}
