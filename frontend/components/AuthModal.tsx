"use client";

import { ArrowRight, Check, Eye, EyeOff, Loader2, Scale, ShieldCheck } from "lucide-react";
import { useState } from "react";
import BrandLogo from "@/components/BrandLogo";
import { ApiError, login, register } from "@/lib/api";
import type { IngestionProgress, User } from "@/lib/types";

export default function AuthModal({ onSuccess, progress }: { onSuccess: (user: User) => void; progress?: IngestionProgress | null }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault(); setError(""); setLoading(true);
    try { onSuccess(mode === "login" ? await login(email, password) : await register(name, email, password)); }
    catch (err) { setError(err instanceof ApiError ? err.message : "Unable to reach the workspace. Please try again."); }
    finally { setLoading(false); }
  };
  return <div className="auth-shell">
    <section className="auth-story" onPointerMove={event => {
      const bounds = event.currentTarget.getBoundingClientRect();
      event.currentTarget.style.setProperty("--research-x", `${event.clientX - bounds.left}px`);
      event.currentTarget.style.setProperty("--research-y", `${event.clientY - bounds.top}px`);
    }}>
      <BrandLogo className="auth-wordmark" />
      <div className="auth-judiciary-copy">
        <p className="auth-kicker"><span>01</span> Corpusil legal intelligence</p>
        <h1>Where law meets<br/><em>verifiable evidence.</em></h1>
        <p>Enter a research space shaped around authority, reasoning and the source—not generic AI answers.</p>
      </div>
      <div className="auth-courtline" aria-hidden="true"><span className="court-dome"/><span className="court-entablature"/><i className="court-column c1"/><i className="court-column c2"/><i className="court-column c3"/><i className="court-column c4"/><span className="court-steps"/><div className="court-scale"><Scale size={49} strokeWidth={1}/></div></div>
      <div className="auth-corpus-status"><span className={progress?.validation_status === "pass" ? "live" : ""}/><p>Corpus online</p><i/><p><strong>{progress?.canonical_documents?.toLocaleString() ?? "—"}</strong> sources</p><i/><p><strong>{(progress?.global_points ?? progress?.qdrant_points)?.toLocaleString() ?? "—"}</strong> passages</p></div>
    </section>
    <section className="auth-entry">
      <div className="auth-panel">
        <div className="auth-mobile-brand"><BrandLogo /></div>
        <div className="auth-panel-top"><span>Private workspace</span><ShieldCheck size={15}/></div>
        <div className="auth-heading"><p>{mode === "login" ? "Welcome back" : "Your account"}</p><h2>{mode === "login" ? "Continue your research." : "Begin with a question."}</h2><span>{mode === "login" ? "Every conversation returns with its own context intact." : "Create a citizen workspace for evidence-grounded legal information."}</span></div>
        <form onSubmit={handleSubmit} className="auth-form">
          {mode === "register" && <label>Full name<input autoComplete="name" value={name} onChange={e => setName(e.target.value)} required minLength={2} className="field" placeholder="Your full name" /></label>}
          <label>Email address<input type="email" autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} required className="field" placeholder="you@example.com" /></label>
          <label>Password<div className="password-field"><input type={showPassword ? "text" : "password"} autoComplete={mode === "login" ? "current-password" : "new-password"} value={password} onChange={e => setPassword(e.target.value)} required minLength={mode === "register" ? 12 : undefined} className="field" placeholder={mode === "login" ? "Enter your password" : "At least 12 characters"} /><button type="button" onClick={() => setShowPassword(value => !value)} aria-label={showPassword ? "Hide password" : "Show password"}>{showPassword ? <EyeOff size={17}/> : <Eye size={17}/>}</button></div></label>
          {error && <p role="alert" className="auth-error">{error}</p>}
          <button type="submit" disabled={loading} className="auth-submit">{loading ? <Loader2 size={17} className="animate-spin" /> : <span>{mode === "login" ? "Enter workspace" : "Create workspace"}</span>}{!loading && <ArrowRight size={17}/>}</button>
        </form>
        <div className="auth-switch"><span>{mode === "login" ? "New to Corpusil?" : "Already have an account?"}</span><button onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }}>{mode === "login" ? "Create an account" : "Sign in"}<ArrowRight size={13}/></button></div>
        <div className="auth-assurance"><span><Check size={12}/>Independent chat context</span><span><Check size={12}/>Source-linked answers</span></div>
      </div>
    </section>
  </div>;
}
