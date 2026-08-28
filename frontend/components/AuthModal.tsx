"use client";

import { ArrowRight, CheckCircle2, FileCheck2, Landmark, Loader2, LockKeyhole, ShieldCheck, X } from "lucide-react";
import { useState } from "react";
import { ApiError, login, register } from "@/lib/api";
import type { IngestionProgress, User } from "@/lib/types";

interface AuthModalProps { onSuccess: (user: User) => void; progress?: IngestionProgress | null; }

const trustPoints = [
  "Grounded answers with page-level citations",
  "Role-isolated police and advocate workspaces",
  "Private evidence separated from the public corpus",
];

export default function AuthModal({ onSuccess, progress }: AuthModalProps) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault(); setError(""); setLoading(true);
    try {
      const user = mode === "login" ? await login(email, password) : await register(name, email, password);
      onSuccess(user);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to reach the secure workspace. Confirm the backend is running.");
    } finally { setLoading(false); }
  };

  return (
    <div className="fixed inset-0 z-50 grid min-h-screen bg-[#f4f6f8] lg:grid-cols-[1.05fr_0.95fr]">
      <section className="relative hidden overflow-hidden bg-[#0b1729] px-12 py-10 text-white lg:flex lg:flex-col">
        <div className="auth-grid absolute inset-0 opacity-30" />
        <div className="absolute -right-32 top-20 h-96 w-96 rounded-full bg-[#176b87]/20 blur-3xl" />
        <div className="relative flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-white/15 bg-white/10"><Landmark size={22} /></div>
          <div><p className="text-base font-semibold tracking-tight">Aegis Legal Intelligence</p><p className="text-[11px] uppercase tracking-[0.22em] text-slate-400">Decision support platform</p></div>
        </div>
        <div className="relative my-auto max-w-xl py-16">
          <div className="mb-7 inline-flex items-center gap-2 rounded-full border border-[#4ab0bd]/25 bg-[#153148] px-3 py-1.5 text-xs font-medium text-[#8ed8dd]"><ShieldCheck size={14} /> Evidence-first legal research</div>
          <h1 className="text-5xl font-semibold leading-[1.08] tracking-[-0.04em]">Legal research built for decisions that matter.</h1>
          <p className="mt-6 max-w-lg text-base leading-7 text-slate-300">Search verified authorities, analyse private case evidence and produce review-ready work with a complete citation trail.</p>
          <div className="mt-9 space-y-4">{trustPoints.map((point) => <div key={point} className="flex items-center gap-3 text-sm text-slate-200"><CheckCircle2 size={18} className="text-[#55c3c8]" />{point}</div>)}</div>
        </div>
        <div className="relative grid grid-cols-3 gap-6 border-t border-white/10 pt-6">
          <div><p className="text-2xl font-semibold">{progress?.canonical_documents?.toLocaleString() ?? "381"}</p><p className="mt-1 text-xs text-slate-400">Canonical sources</p></div>
          <div><p className="text-2xl font-semibold">{(progress?.global_points ?? progress?.qdrant_points) ? `${((progress?.global_points ?? progress?.qdrant_points ?? 0) / 1000).toFixed(1)}K` : "25.5K"}</p><p className="mt-1 text-xs text-slate-400">Verified passages</p></div>
          <div><p className="text-2xl font-semibold">100%</p><p className="mt-1 text-xs text-slate-400">Locally controlled</p></div>
        </div>
      </section>

      <section className="flex items-center justify-center px-6 py-10 sm:px-12">
        <div className="w-full max-w-[440px]">
          <div className="mb-10 flex items-center gap-3 lg:hidden"><div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#0b1729] text-white"><Landmark size={20} /></div><p className="font-semibold text-[#142033]">Aegis Legal Intelligence</p></div>
          <div className="mb-8">
            <p className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-[#167184]">Secure access</p>
            <h2 className="text-3xl font-semibold tracking-[-0.03em] text-[#101828]">{mode === "login" ? "Welcome back" : "Create your workspace"}</h2>
            <p className="mt-3 text-sm leading-6 text-[#667085]">{mode === "login" ? "Sign in to continue to the legal intelligence console." : "Create a citizen account to begin grounded legal research."}</p>
          </div>
          <form onSubmit={handleSubmit} className="space-y-5">
            {mode === "register" && <label className="block text-sm font-medium text-[#344054]">Full name<input type="text" value={name} onChange={(e) => setName(e.target.value)} required minLength={2} className="field mt-2" placeholder="Enter your full name" /></label>}
            <label className="block text-sm font-medium text-[#344054]">Work email<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required className="field mt-2" placeholder="name@organisation.com" /></label>
            <label className="block text-sm font-medium text-[#344054]">Password<div className="relative mt-2"><LockKeyhole size={17} className="absolute left-3.5 top-3.5 text-[#98a2b3]" /><input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={12} className="field pl-11" placeholder="Minimum 12 characters" /></div></label>
            {error && <div role="alert" className="flex items-start gap-2 rounded-xl border border-[#fecdca] bg-[#fef3f2] px-4 py-3 text-sm text-[#b42318]"><X size={16} className="mt-0.5 shrink-0" />{error}</div>}
            <button type="submit" disabled={loading} className="flex w-full items-center justify-center gap-2 rounded-xl bg-[#0b1729] px-4 py-3.5 text-sm font-semibold text-white shadow-sm transition hover:bg-[#16263d] disabled:opacity-50">{loading ? <Loader2 size={17} className="animate-spin" /> : <>{mode === "login" ? "Sign in securely" : "Create account"}<ArrowRight size={17} /></>}</button>
          </form>
          <p className="mt-7 text-center text-sm text-[#667085]">{mode === "login" ? "New to the platform?" : "Already have an account?"} <button onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }} className="font-semibold text-[#167184] hover:text-[#105a69]">{mode === "login" ? "Create an account" : "Sign in"}</button></p>
          <div className="mt-10 flex items-center justify-center gap-2 text-xs text-[#98a2b3]"><FileCheck2 size={14} /> Grounded outputs require professional review</div>
        </div>
      </section>
    </div>
  );
}
