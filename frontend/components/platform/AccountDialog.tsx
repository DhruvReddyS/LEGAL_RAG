"use client";

import { Copy, Download, KeyRound, Laptop, Loader2, ShieldCheck, Trash2, Type, UserRound, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useDialogFocus } from "@/components/useDialogFocus";
import { ApiError } from "@/lib/api";
import {
  adminEraseAccount,
  adminIssueResetCode,
  adminRetentionStatus,
  adminRunRetention,
  beginMfaEnrollment,
  changePassword,
  confirmMfaEnrollment,
  disableMfa,
  downloadMyData,
  eraseMyAccount,
  getAccountStatus,
  listDeviceSessions,
  replaceRecoveryCodes,
  revokeDeviceSession,
  revokeOtherSessions,
  updateProfile,
  withdrawConsent,
} from "@/lib/api-platform";
import { formatRelativeDay } from "@/lib/history-view";
import { readPreferences, savePreferences, TEXT_SIZES, type ReadingPreferences } from "@/lib/preferences";
import { SITE_ROUTES } from "@/lib/site";
import type { AccountStatus, AdminResetCode, DeviceSession, RetentionStatus } from "@/lib/types-platform";
import type { User } from "@/lib/types";

const ERASE_PHRASE = "ERASE MY ACCOUNT";
const ADMIN_ERASE_PHRASE = "ERASE THIS ACCOUNT";

type Tab = "profile" | "security" | "devices" | "data" | "reading" | "admin";

const explain = (error: unknown, fallback = "That did not work. Please try again.") => {
  if (!(error instanceof ApiError)) return fallback;
  if (error.message === "mfa_required") return "Enter a code from your authenticator, or a recovery code.";
  if (error.message === "mfa_invalid") return "That code is not correct, or it has already been used.";
  return error.message;
};

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function Feedback({ error, success }: { error?: string; success?: string }) {
  if (error) return <p role="alert" className="auth-error">{error}</p>;
  if (success) return <p role="status" className="acct-success">{success}</p>;
  return null;
}

/** Password plus, when two-step sign-in is on, a code. For anything irreversible. */
function StepUpFields({ mfaEnabled, password, setPassword, code, setCode }: { mfaEnabled: boolean; password: string; setPassword: (value: string) => void; code: string; setCode: (value: string) => void }) {
  return (
    <>
      <label>Your password
        <input className="field" type="password" autoComplete="current-password" required value={password} onChange={event => setPassword(event.target.value)} />
      </label>
      {mfaEnabled && (
        <label>Authenticator or recovery code
          <input className="field" autoComplete="one-time-code" required value={code} onChange={event => setCode(event.target.value)} />
        </label>
      )}
    </>
  );
}

const stepUpBody = (password: string, code: string) => {
  const cleaned = code.trim();
  return { password, ...(cleaned ? (/^[\d\s]{6,8}$/.test(cleaned) ? { mfa_code: cleaned } : { recovery_code: cleaned }) : {}) };
};

function RecoveryCodeList({ codes }: { codes: string[] }) {
  const [copied, setCopied] = useState(false);
  const text = codes.join("\n");
  return (
    <div className="recovery-codes">
      <p><strong>Save these now.</strong> They are shown once. Each one gets you in once if you lose your authenticator.</p>
      <ul>{codes.map(code => <li key={code}><code>{code}</code></li>)}</ul>
      <div className="acct-row-actions">
        <button type="button" className="button-secondary" onClick={() => { void navigator.clipboard?.writeText(text).then(() => setCopied(true)); }}><Copy size={14} aria-hidden="true" />{copied ? "Copied" : "Copy"}</button>
        <button type="button" className="button-secondary" onClick={() => saveBlob(new Blob([text + "\n"], { type: "text/plain" }), "corpusil-recovery-codes.txt")}><Download size={14} aria-hidden="true" />Save as a file</button>
      </div>
    </div>
  );
}

function ProfileTab({ user, onUserChange }: { user: User; onUserChange: (user: User) => void }) {
  const [name, setName] = useState(user.name);
  const [email, setEmail] = useState(user.email);
  const [password, setPassword] = useState("");
  const [state, setState] = useState<{ error?: string; success?: string }>({});
  const emailChanged = email.trim().toLowerCase() !== user.email;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setState({});
    try {
      const updated = await updateProfile({
        ...(name !== user.name ? { name } : {}),
        ...(emailChanged ? { email: email.trim(), current_password: password } : {}),
      });
      onUserChange(updated);
      setPassword("");
      setState({ success: "Saved." });
    } catch (failure) {
      setState({ error: explain(failure) });
    }
  };

  return (
    <section aria-labelledby="acct-profile">
      <h3 id="acct-profile">Your details</h3>
      <p className="acct-hint">Correct what is held about you. Your email address is how you sign in.</p>
      <form className="auth-form" onSubmit={submit}>
        <label>Name<input className="field" autoComplete="name" minLength={2} required value={name} onChange={event => setName(event.target.value)} /></label>
        <label>Email address<input className="field" type="email" autoComplete="email" required value={email} onChange={event => setEmail(event.target.value)} /></label>
        {emailChanged && <label>Your password, to change the address<input className="field" type="password" autoComplete="current-password" required value={password} onChange={event => setPassword(event.target.value)} /></label>}
        <Feedback {...state} />
        <button className="button-primary acct-submit" disabled={name === user.name && !emailChanged}>Save</button>
      </form>
    </section>
  );
}

function SecurityTab({ status, reload }: { status: AccountStatus; reload: () => void }) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [passwordState, setPasswordState] = useState<{ error?: string; success?: string }>({});

  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [enrollment, setEnrollment] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [codes, setCodes] = useState<string[] | null>(null);
  const [mfaState, setMfaState] = useState<{ error?: string; success?: string }>({});

  const submitPassword = async (event: React.FormEvent) => {
    event.preventDefault();
    setPasswordState({});
    try {
      await changePassword(currentPassword, newPassword);
      setCurrentPassword("");
      setNewPassword("");
      setPasswordState({ success: "Password changed. Other devices have been signed out." });
      reload();
    } catch (failure) {
      setPasswordState({ error: explain(failure) });
    }
  };

  const run = (work: () => Promise<void>) => async (event: React.FormEvent) => {
    event.preventDefault();
    setMfaState({});
    try {
      await work();
    } catch (failure) {
      setMfaState({ error: explain(failure) });
    }
  };

  return (
    <>
      <section aria-labelledby="acct-password">
        <h3 id="acct-password">Password</h3>
        <form className="auth-form" onSubmit={submitPassword}>
          <label>Current password<input className="field" type="password" autoComplete="current-password" required value={currentPassword} onChange={event => setCurrentPassword(event.target.value)} /></label>
          <label>New password, at least 12 characters<input className="field" type="password" autoComplete="new-password" required minLength={12} maxLength={72} value={newPassword} onChange={event => setNewPassword(event.target.value)} /></label>
          <Feedback {...passwordState} />
          <button className="button-primary acct-submit">Change password</button>
        </form>
      </section>

      <section aria-labelledby="acct-mfa">
        <h3 id="acct-mfa">Two-step sign-in</h3>
        {codes && <RecoveryCodeList codes={codes} />}
        {status.mfa_enabled ? (
          <>
            <p className="acct-hint"><span className="acct-state is-on">On.</span> {status.recovery_codes_remaining} recovery codes left.</p>
            <form className="auth-form" onSubmit={run(async () => { await disableMfa(stepUpBody(password, code)); setPassword(""); setCode(""); setCodes(null); setMfaState({ success: "Two-step sign-in is off." }); reload(); })}>
              <StepUpFields mfaEnabled password={password} setPassword={setPassword} code={code} setCode={setCode} />
              <Feedback {...mfaState} />
              <div className="acct-row-actions">
                <button className="button-secondary">Turn off</button>
                <button type="button" className="button-secondary" onClick={() => { void run(async () => { const result = await replaceRecoveryCodes(stepUpBody(password, code)); setCodes(result.codes); setPassword(""); setCode(""); reload(); })({ preventDefault() {} } as React.FormEvent); }}>Replace recovery codes</button>
              </div>
            </form>
          </>
        ) : enrollment ? (
          <form className="auth-form" onSubmit={run(async () => { const result = await confirmMfaEnrollment(code); setCodes(result.codes); setEnrollment(null); setCode(""); setPassword(""); setMfaState({ success: "Two-step sign-in is on." }); reload(); })}>
            <p className="acct-hint">In your authenticator app, add an account by entering this key, or open the link on a phone. Then type the code it shows.</p>
            <p className="mfa-secret"><code>{enrollment.secret.match(/.{1,4}/g)?.join(" ")}</code></p>
            <p className="acct-hint"><a href={enrollment.otpauth_uri}>Open in an authenticator app</a></p>
            <label>Code from your app<input className="field" inputMode="numeric" autoComplete="one-time-code" required value={code} onChange={event => setCode(event.target.value)} /></label>
            <Feedback {...mfaState} />
            <button className="button-primary acct-submit">Confirm</button>
          </form>
        ) : (
          <form className="auth-form" onSubmit={run(async () => { setEnrollment(await beginMfaEnrollment(password)); setPassword(""); })}>
            <p className="acct-hint"><span className="acct-state">Off.</span> A password alone is one leak away from your account. If you hold police or client material, turn this on. Any authenticator app works.</p>
            <label>Your password<input className="field" type="password" autoComplete="current-password" required value={password} onChange={event => setPassword(event.target.value)} /></label>
            <Feedback {...mfaState} />
            <button className="button-primary acct-submit">Set up</button>
          </form>
        )}
      </section>
    </>
  );
}

function DevicesTab() {
  const [devices, setDevices] = useState<DeviceSession[] | null>(null);
  const [state, setState] = useState<{ error?: string; success?: string }>({});
  const load = useCallback(() => {
    listDeviceSessions().then(setDevices).catch(() => { setDevices([]); setState({ error: "Your devices could not be loaded." }); });
  }, []);
  useEffect(load, [load]);

  const revoke = async (device: DeviceSession) => {
    setState({});
    try {
      await revokeDeviceSession(device.id);
      setState({ success: `${device.label} is signed out.` });
      load();
    } catch (failure) {
      setState({ error: explain(failure) });
    }
  };
  const revokeOthers = async () => {
    setState({});
    try {
      const { revoked } = await revokeOtherSessions();
      setState({ success: revoked === 1 ? "1 other device is signed out." : `${revoked} other devices are signed out.` });
      load();
    } catch (failure) {
      setState({ error: explain(failure) });
    }
  };

  return (
    <section aria-labelledby="acct-devices">
      <h3 id="acct-devices">Where you are signed in</h3>
      <p className="acct-hint">Signing a device out takes effect immediately. Only a device&rsquo;s browser and system are recorded, not its location or address.</p>
      {devices === null ? <p role="status" className="acct-hint">Loading&hellip;</p> : (
        <ul className="device-list">
          {devices.map(device => (
            <li key={device.id}>
              <Laptop size={17} aria-hidden="true" />
              <div>
                <strong>{device.label}{device.current && <span className="acct-state is-on"> This device</span>}</strong>
                <small>Last active {formatRelativeDay(device.last_seen_at).toLowerCase()}</small>
              </div>
              {!device.current && <button type="button" className="button-secondary" onClick={() => void revoke(device)} aria-label={`Sign out ${device.label}`}>Sign out</button>}
            </li>
          ))}
          {devices.length === 0 && <li className="acct-hint">No devices are listed. Sessions started before this feature appear after their next refresh.</li>}
        </ul>
      )}
      <Feedback {...state} />
      {(devices?.length ?? 0) > 1 && <button type="button" className="button-secondary" onClick={() => void revokeOthers()}>Sign out all other devices</button>}
    </section>
  );
}

function DataTab({ user, status, reload, onSignOut, onErased }: { user: User; status: AccountStatus; reload: () => void; onSignOut: () => void; onErased: (receipt: string) => void }) {
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [state, setState] = useState<{ error?: string; success?: string }>({});
  const [erasePassword, setErasePassword] = useState("");
  const [eraseCode, setEraseCode] = useState("");
  const [phrase, setPhrase] = useState("");
  const [eraseState, setEraseState] = useState<{ error?: string; success?: string }>({});
  const [busy, setBusy] = useState(false);
  const [withdrawing, setWithdrawing] = useState(false);
  const professional = user.role === "police" || user.role === "advocate";

  const exportData = async (event: React.FormEvent) => {
    event.preventDefault();
    setState({});
    setBusy(true);
    try {
      saveBlob(await downloadMyData(stepUpBody(password, code)), "corpusil-my-data.json");
      setPassword("");
      setCode("");
      setState({ success: "Your data has been downloaded." });
    } catch (failure) {
      setState({ error: explain(failure) });
    } finally {
      setBusy(false);
    }
  };

  const erase = async (event: React.FormEvent) => {
    event.preventDefault();
    setEraseState({});
    setBusy(true);
    try {
      const receipt = await eraseMyAccount(stepUpBody(erasePassword, eraseCode), phrase);
      onErased(receipt.receipt_id);
    } catch (failure) {
      setEraseState({ error: explain(failure) });
      setBusy(false);
    }
  };

  return (
    <>
      <section aria-labelledby="acct-export">
        <h3 id="acct-export">Download your data</h3>
        <p className="acct-hint">One JSON file with your account, conversations, sources and any case records. Keep it safe: it is everything in one place.</p>
        <form className="auth-form" onSubmit={exportData}>
          <StepUpFields mfaEnabled={status.mfa_enabled} password={password} setPassword={setPassword} code={code} setCode={setCode} />
          <Feedback {...state} />
          <button className="button-primary acct-submit" disabled={busy}><Download size={15} aria-hidden="true" />Download</button>
        </form>
      </section>

      <section aria-labelledby="acct-consent">
        <h3 id="acct-consent">Consent</h3>
        <p className="acct-hint">
          {status.consent.required
            ? "You have not accepted the current privacy notice."
            : `You accepted notice version ${status.consent.accepted_version}${status.consent.accepted_at ? ` on ${new Date(status.consent.accepted_at).toLocaleDateString("en-IN")}` : ""}.`}{" "}
          <Link href={SITE_ROUTES.privacy} target="_blank" rel="noopener">Read the notice</Link>.
        </p>
        {!status.consent.required && (withdrawing ? (
          <div className="acct-confirm">
            <p>Withdrawing stops processing for your account: you will not be able to use the app until you accept again or erase it. Nothing is deleted by this alone.</p>
            <div className="acct-row-actions">
              <button type="button" className="button-secondary" onClick={() => setWithdrawing(false)}>Keep consent</button>
              <button type="button" className="button-secondary" onClick={() => { void withdrawConsent().then(() => { setWithdrawing(false); reload(); onSignOut(); }); }}>Withdraw and sign out</button>
            </div>
          </div>
        ) : <button type="button" className="button-secondary" onClick={() => setWithdrawing(true)}>Withdraw consent</button>)}
      </section>

      <section aria-labelledby="acct-erase" className="acct-danger">
        <h3 id="acct-erase"><Trash2 size={15} aria-hidden="true" /> Erase your account</h3>
        <p className="acct-hint">
          Removes your account, conversations, case records and uploaded files from the database, the search index and file
          storage, including earlier versions. It cannot be undone. Download your data first if you want a copy.
        </p>
        {professional && (
          <p className="acct-warning">
            <strong>This also removes your case records.</strong> If they are official records, or client files you must keep
            by law or professional rule, export them and check your obligations first. This action does not know about them.
          </p>
        )}
        <form className="auth-form" onSubmit={erase}>
          <StepUpFields mfaEnabled={status.mfa_enabled} password={erasePassword} setPassword={setErasePassword} code={eraseCode} setCode={setEraseCode} />
          <label><span>Type <code>{ERASE_PHRASE}</code> to confirm</span>
            <input className="field" autoComplete="off" required value={phrase} onChange={event => setPhrase(event.target.value)} />
          </label>
          <Feedback {...eraseState} />
          <button className="button-danger acct-submit" disabled={busy || phrase !== ERASE_PHRASE}>Erase everything</button>
        </form>
      </section>
    </>
  );
}

function ReadingTab() {
  const [preferences, setPreferences] = useState<ReadingPreferences>(() => readPreferences());
  const update = (changes: Partial<ReadingPreferences>) => {
    const next = { ...preferences, ...changes };
    setPreferences(next);
    savePreferences(next);
  };
  return (
    <section aria-labelledby="acct-reading">
      <h3 id="acct-reading">Reading on this device</h3>
      <fieldset className="acct-choice">
        <legend>Text size</legend>
        {TEXT_SIZES.map(size => (
          <label key={size.value}>
            <input type="radio" name="text-size" checked={preferences.textSize === size.value} onChange={() => update({ textSize: size.value })} />
            <span>{size.label}</span>
          </label>
        ))}
      </fieldset>
      <label className="acct-toggle">
        <input type="checkbox" checked={preferences.lowBandwidth} onChange={event => update({ lowBandwidth: event.target.checked })} />
        <span>
          <strong>Low-bandwidth mode</strong>
          <small>Drops background decoration and status checks, and loads fewer conversations at a time. Answers are unchanged.</small>
        </span>
      </label>
    </section>
  );
}

function AdminTab() {
  const [email, setEmail] = useState("");
  const [resetMfa, setResetMfa] = useState(false);
  const [issued, setIssued] = useState<AdminResetCode | null>(null);
  const [resetState, setResetState] = useState<{ error?: string; success?: string }>({});

  const [eraseEmail, setEraseEmail] = useState("");
  const [erasePassword, setErasePassword] = useState("");
  const [eraseCode, setEraseCode] = useState("");
  const [phrase, setPhrase] = useState("");
  const [eraseState, setEraseState] = useState<{ error?: string; success?: string }>({});

  const [retention, setRetention] = useState<RetentionStatus | null>(null);
  const [retentionState, setRetentionState] = useState<{ error?: string; success?: string }>({});
  const loadRetention = useCallback(() => { adminRetentionStatus().then(setRetention).catch(() => setRetention(null)); }, []);
  useEffect(loadRetention, [loadRetention]);

  const issue = async (event: React.FormEvent) => {
    event.preventDefault();
    setResetState({});
    setIssued(null);
    try {
      setIssued(await adminIssueResetCode(email.trim(), resetMfa));
    } catch (failure) {
      setResetState({ error: explain(failure) });
    }
  };

  const erase = async (event: React.FormEvent) => {
    event.preventDefault();
    setEraseState({});
    try {
      const receipt = await adminEraseAccount(eraseEmail.trim(), erasePassword, phrase, eraseCode.trim());
      setEraseState({ success: `Erased. Receipt ${receipt.receipt_id}.` });
      setEraseEmail("");
      setErasePassword("");
      setEraseCode("");
      setPhrase("");
    } catch (failure) {
      setEraseState({ error: explain(failure) });
    }
  };

  const runRetention = async () => {
    setRetentionState({});
    try {
      const { erased_conversations: erased } = await adminRunRetention();
      setRetentionState({ success: `${erased} conversations erased.` });
      loadRetention();
    } catch (failure) {
      setRetentionState({ error: explain(failure) });
    }
  };

  return (
    <>
      <section aria-labelledby="acct-admin-reset">
        <h3 id="acct-admin-reset">Issue a password reset code</h3>
        <p className="acct-hint">For someone who cannot sign in. No email is sent: hand the code over in person or on a channel you trust. It works once, and you never see the new password.</p>
        <form className="auth-form" onSubmit={issue}>
          <label>Their email address<input className="field" type="email" required value={email} onChange={event => setEmail(event.target.value)} /></label>
          <label className="acct-inline"><input type="checkbox" checked={resetMfa} onChange={event => setResetMfa(event.target.checked)} /> Also clear two-step sign-in, if they lost their authenticator and recovery codes</label>
          <Feedback {...resetState} />
          <button className="button-primary acct-submit">Issue code</button>
        </form>
        {issued && (
          <div className="recovery-codes" role="status">
            <p><strong>Shown once.</strong> It expires {new Date(issued.expires_at).toLocaleString("en-IN")}.{issued.mfa_cleared ? " Their two-step sign-in has been cleared." : ""}</p>
            <p className="mfa-secret"><code>{issued.code}</code></p>
          </div>
        )}
      </section>

      <section aria-labelledby="acct-admin-retention">
        <h3 id="acct-admin-retention">Retention</h3>
        {retention ? (
          <p className="acct-hint">
            {retention.chats_kept_until_deleted
              ? "No retention period is set: conversations stay until their owner deletes them. Set CHAT_RETENTION_DAYS in the environment to change this."
              : `Conversations with no activity for ${retention.chat_retention_days} days are erased when this runs. ${retention.conversations_past_retention} are past that now.`}
          </p>
        ) : <p className="acct-hint">The retention status could not be read.</p>}
        <Feedback {...retentionState} />
        {retention && !retention.chats_kept_until_deleted && <button type="button" className="button-secondary" onClick={() => void runRetention()}>Run retention now</button>}
      </section>

      <section aria-labelledby="acct-admin-erase" className="acct-danger">
        <h3 id="acct-admin-erase"><Trash2 size={15} aria-hidden="true" /> Erase an account on request</h3>
        <p className="acct-hint">For someone who cannot sign in. It removes their data without showing you any of it, and cannot be undone. Confirm who is asking first.</p>
        <form className="auth-form" onSubmit={erase}>
          <label>Their email address<input className="field" type="email" required value={eraseEmail} onChange={event => setEraseEmail(event.target.value)} /></label>
          <label>Your password<input className="field" type="password" autoComplete="current-password" required value={erasePassword} onChange={event => setErasePassword(event.target.value)} /></label>
          <label>Your authenticator code, if you have one<input className="field" autoComplete="one-time-code" value={eraseCode} onChange={event => setEraseCode(event.target.value)} /></label>
          <label><span>Type <code>{ADMIN_ERASE_PHRASE}</code> to confirm</span><input className="field" autoComplete="off" required value={phrase} onChange={event => setPhrase(event.target.value)} /></label>
          <Feedback {...eraseState} />
          <button className="button-danger acct-submit" disabled={phrase !== ADMIN_ERASE_PHRASE}>Erase this account</button>
        </form>
      </section>
    </>
  );
}

export default function AccountDialog({ user, onClose, onUserChange, onSignOut, onErased }: { user: User; onClose: () => void; onUserChange: (user: User) => void; onSignOut: () => void; onErased: (receipt: string) => void }) {
  const ref = useDialogFocus(true, onClose);
  const [tab, setTab] = useState<Tab>("security");
  const [status, setStatus] = useState<AccountStatus | null>(null);
  const [failed, setFailed] = useState(false);
  const reload = useCallback(() => {
    getAccountStatus().then(next => { setStatus(next); setFailed(false); }).catch(() => setFailed(true));
  }, []);
  useEffect(reload, [reload]);

  const tabs: ReadonlyArray<{ id: Tab; label: string; icon: typeof KeyRound }> = [
    { id: "security", label: "Sign-in", icon: KeyRound },
    { id: "devices", label: "Devices", icon: Laptop },
    { id: "data", label: "Your data", icon: ShieldCheck },
    { id: "profile", label: "Details", icon: UserRound },
    { id: "reading", label: "Reading", icon: Type },
    ...(user.role === "admin" ? [{ id: "admin" as const, label: "Administration", icon: ShieldCheck }] : []),
  ];

  return (
    <div className="modal-backdrop acct-backdrop" onMouseDown={onClose}>
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby="acct-title" className="acct-dialog" onMouseDown={event => event.stopPropagation()}>
        <div className="acct-head">
          <h2 id="acct-title">Account and privacy</h2>
          <button type="button" className="icon-button" aria-label="Close account and privacy" onClick={onClose}><X size={18} /></button>
        </div>
        <div className="acct-tabs" role="tablist" aria-label="Account sections">
          {tabs.map(item => (
            <button key={item.id} type="button" role="tab" aria-selected={tab === item.id} onClick={() => setTab(item.id)}>
              <item.icon size={15} aria-hidden="true" />{item.label}
            </button>
          ))}
        </div>
        <div className="acct-panel" role="tabpanel">
          {tab === "reading" ? <ReadingTab />
            : tab === "devices" ? <DevicesTab />
            : tab === "profile" ? <ProfileTab user={user} onUserChange={onUserChange} />
            : tab === "admin" ? <AdminTab />
            : failed ? <p role="alert" className="auth-error">Your account status could not be loaded. Check your connection and try again.</p>
            : !status ? <p role="status" className="acct-hint"><Loader2 size={15} className="animate-spin inline" aria-hidden="true" /> Loading&hellip;</p>
            : tab === "security" ? <SecurityTab status={status} reload={reload} />
            : <DataTab user={user} status={status} reload={reload} onSignOut={onSignOut} onErased={onErased} />}
        </div>
      </div>
    </div>
  );
}
