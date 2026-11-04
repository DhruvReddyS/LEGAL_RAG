"use client";

import { ArrowRight, Eye, EyeOff, Loader2, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import BrandLogo from "@/components/BrandLogo";
import ForgotPassword from "@/components/platform/ForgotPassword";
import { ApiError, login, register } from "@/lib/api";
import { PRIVACY_NOTICE_VERSION } from "@/lib/privacy-text";
import { SITE_ROUTES } from "@/lib/site";
import type { IngestionProgress, User } from "@/lib/types";

/**
 * The sign-in surface.
 *
 * The previous version drew a courthouse in CSS -- dome, columns, steps -- ran
 * a gradient that followed the pointer, animated a light along a rule, and
 * opened with "Where law meets verifiable evidence". That is the register of a
 * product launch, and this is a tool police officers and advocates open at
 * their desks.
 *
 * What replaces it is what the system will and will not do, stated plainly,
 * with the corpus figures beside it. A person deciding whether to trust a
 * legal research tool wants to know what it refuses to do; nobody was ever
 * persuaded by a drawn colonnade.
 */

const GUARANTEES = [
  "Every published statement cites a source that was actually retrieved.",
  "Repealed provisions are labelled, and what replaced them is named.",
  "When the corpus cannot answer, it says so rather than improvising.",
];

export default function AuthModal({ onSuccess, progress }: { onSuccess: (user: User) => void; progress?: IngestionProgress | null }) {
  const [mode, setMode] = useState<"login" | "register" | "forgot">("login");
  const [needsCode, setNeedsCode] = useState(false);
  const [code, setCode] = useState("");
  const [consented, setConsented] = useState(false);
  const [notice, setNotice] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault(); setError(""); setNotice(""); setLoading(true);
    const typed = code.trim();
    const secondFactor = !needsCode || !typed ? {} : /^[\d\s]{6,8}$/.test(typed) ? { mfa_code: typed } : { recovery_code: typed };
    try { onSuccess(mode === "login" ? await login(email, password, secondFactor) : await register(name, email, password, PRIVACY_NOTICE_VERSION)); }
    catch (err) {
      if (err instanceof ApiError && err.message === "mfa_required") { setNeedsCode(true); }
      else if (err instanceof ApiError && err.message === "mfa_invalid") { setNeedsCode(true); setError("That code is not correct, or it has already been used."); }
      else setError(err instanceof ApiError ? err.message : "Unable to reach the workspace. Please try again.");
    }
    finally { setLoading(false); }
  };

  const documents = progress?.canonical_documents?.toLocaleString();
  const passages = (progress?.global_points ?? progress?.qdrant_points)?.toLocaleString();

  return <div className="auth-shell">
    <section className="auth-story">
      <BrandLogo className="auth-wordmark" />

      <div className="auth-story-body">
        <h1>Indian legal research,<br/>answered from the source.</h1>
        <p className="auth-lede">
          Statute, rules and judgments in one governed corpus, with the 2023
          Sanhitas and the codes they replaced held side by side.
        </p>

        <ul className="auth-guarantees">
          {GUARANTEES.map(line => <li key={line}>{line}</li>)}
        </ul>
      </div>

      <dl className="auth-figures">
        <div>
          <dt>Sources</dt>
          <dd>{documents ?? "—"}</dd>
        </div>
        <div>
          <dt>Indexed passages</dt>
          <dd>{passages ?? "—"}</dd>
        </div>
        <div>
          <dt>Corpus</dt>
          <dd className="auth-figure-state">
            <span className={progress?.validation_status === "pass" ? "is-live" : ""} />
            {progress?.validation_status === "pass" ? "Verified" : "Checking"}
          </dd>
        </div>
      </dl>
    </section>

    <section className="auth-entry">
      <div className="auth-panel">
        <div className="auth-mobile-brand"><BrandLogo /></div>
        <div className="auth-panel-top"><span>Private workspace</span><ShieldCheck size={15}/></div>

        {mode === "forgot" ? <ForgotPassword initialEmail={email} onBack={() => setMode("login")} onDone={(address) => { setEmail(address); setPassword(""); setMode("login"); setNotice("Password changed. Sign in with your new password."); }} /> : <>
        <div className="auth-heading">
          <h2>{needsCode ? "Two-step sign-in" : mode === "login" ? "Sign in" : "Create an account"}</h2>
          <span>
            {needsCode
              ? "Enter the code from your authenticator app, or one of your recovery codes."
              : mode === "login"
              ? "Your conversations and matters return with their context intact."
              : "Citizen accounts are created here. Police and advocate accounts are provisioned by an administrator."}
          </span>
        </div>

        {notice && <p role="status" className="acct-success">{notice}</p>}
        <form onSubmit={handleSubmit} className="auth-form">
          {needsCode ? (
            <label>Code
              <input autoFocus autoComplete="one-time-code" value={code} onChange={e => setCode(e.target.value)} required maxLength={32} className="field" />
            </label>
          ) : <>
          {mode === "register" && (
            <label>Full name
              <input autoComplete="name" value={name} onChange={e => setName(e.target.value)} required minLength={2} className="field" placeholder="Your full name" />
            </label>
          )}
          <label>Email address
            <input type="email" autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} required className="field" placeholder="you@example.com" />
          </label>
          <label>Password
            <div className="password-field">
              <input
                type={showPassword ? "text" : "password"}
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
                minLength={mode === "register" ? 12 : undefined}
                className="field"
                placeholder={mode === "login" ? "Enter your password" : "At least 12 characters"}
              />
              <button type="button" onClick={() => setShowPassword(value => !value)} aria-label={showPassword ? "Hide password" : "Show password"}>
                {showPassword ? <EyeOff size={17}/> : <Eye size={17}/>}
              </button>
            </div>
          </label>
          {mode === "register" && (
            <label className="auth-consent">
              <input type="checkbox" required checked={consented} onChange={e => setConsented(e.target.checked)} />
              <span>I have read the <Link href={SITE_ROUTES.privacy} target="_blank" rel="noopener">privacy notice</Link> and accept it and the <Link href={SITE_ROUTES.terms} target="_blank" rel="noopener">terms of use</Link>.</span>
            </label>
          )}
          </>}
          {error && <p role="alert" className="auth-error">{error}</p>}
          <button type="submit" disabled={loading} className="auth-submit">
            {loading ? <Loader2 size={17} className="animate-spin" /> : <span>{needsCode ? "Continue" : mode === "login" ? "Sign in" : "Create account"}</span>}
            {!loading && <ArrowRight size={17}/>}
          </button>
        </form>

        {mode === "login" && !needsCode && <button type="button" className="auth-link" style={{ marginTop: 12 }} onClick={() => { setMode("forgot"); setError(""); setNotice(""); }}>Forgot your password?</button>}
        {needsCode && <button type="button" className="auth-link" style={{ marginTop: 12 }} onClick={() => { setNeedsCode(false); setCode(""); setError(""); }}>Back</button>}
        <div className="auth-switch">
          <span>{mode === "login" ? "No account yet?" : "Already registered?"}</span>
          <button onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); setNeedsCode(false); }}>
            {mode === "login" ? "Create one" : "Sign in"}<ArrowRight size={13}/>
          </button>
        </div>
        </>}

        <p className="auth-footnote">
          Legal information, not advice. Check the current official text before
          relying on any answer in a live matter.
        </p>
        <nav className="auth-footer-links" aria-label="About Corpusil">
          <Link href={SITE_ROUTES.welcome}>About</Link>
          <Link href={SITE_ROUTES.help}>Help</Link>
          <Link href={SITE_ROUTES.privacy}>Privacy</Link>
          <Link href={SITE_ROUTES.terms}>Terms</Link>
        </nav>
      </div>
    </section>
  </div>;
}
