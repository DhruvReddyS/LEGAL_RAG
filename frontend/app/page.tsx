"use client";

import { BookOpenText, BriefcaseBusiness, CheckCircle2, ChevronRight, Command, Database, Gauge, Landmark, LogOut, Menu, ScanSearch, Search, ShieldCheck, UserRound } from "lucide-react";
import { useEffect, useState } from "react";
import AuthModal from "@/components/AuthModal";
import ChatInput from "@/components/ChatInput";
import MessageBubble from "@/components/MessageBubble";
import ProfessionalWorkspace from "@/components/ProfessionalWorkspace";
import RoleDashboard from "@/components/RoleDashboard";
import CommandPalette from "@/components/CommandPalette";
import AdminWorkspace from "@/components/AdminWorkspace";
import DesktopReadiness from "@/components/DesktopReadiness";
import { ApiError, chatWithCorpus, getIngestionProgress, getMe, logout, refreshSession } from "@/lib/api";
import type { ChatMessage, IngestionProgress, RequestedResponseMode, User } from "@/lib/types";

const ROLE_EXPERIENCES = {
  citizen: {
    nav: "Legal help & research",
    workspace: "My legal research",
    eyebrow: "Citizen legal information",
    heading: "What legal issue can we help you understand?",
    description: "Receive plain-language legal information, practical procedural steps and page-linked authorities. The assistant abstains when the verified corpus is insufficient.",
    placeholder: "Describe your legal question in your own words…",
    badge: "Citizen assistant",
    suggestions: [
      { title: "Police complaint", text: "How do I report a cognizable offence and what details should I preserve?" },
      { title: "Missing property", text: "What information should I give police when reporting missing property?" },
      { title: "Fundamental rights", text: "Explain the right to equality under Article 14 in plain language." },
      { title: "Contract basics", text: "What are the essential elements of a valid contract?" },
    ],
  },
  police: {
    nav: "Investigation research",
    workspace: "Police case operations",
    eyebrow: "Police procedural intelligence",
    heading: "Research the lawful next investigative step",
    description: "Check governing authority, procedural duties and evidence gaps. Case operations keep uploaded material isolated to the selected police matter.",
    placeholder: "Ask about procedure, evidence handling or governing provisions…",
    badge: "Police assistant",
    suggestions: [
      { title: "FIR threshold", text: "Is FIR registration mandatory for cognizable offences?" },
      { title: "Evidence integrity", text: "Analyse the procedural safeguards for preserving electronic evidence and chain of custody." },
      { title: "Arrest safeguards", text: "What safeguards and documentation apply during arrest?" },
      { title: "Investigation review", text: "Compare the duties to record information under CrPC section 154 and BNSS section 173." },
    ],
  },
  advocate: {
    nav: "Authority research",
    workspace: "Advocate case strategy",
    eyebrow: "Advocate research intelligence",
    heading: "Build an authority-grounded legal position",
    description: "Research governing law, adverse authority and two-sided arguments. Private client evidence remains isolated to the selected advocate matter.",
    placeholder: "Ask for authority, issue analysis or a two-sided legal position…",
    badge: "Advocate assistant",
    suggestions: [
      { title: "Bail research", text: "Analyse the conditions for bail and the strongest lawful arguments on both sides." },
      { title: "Precedent review", text: "Compare how current Supreme Court authorities treat mandatory FIR registration." },
      { title: "Evidence challenge", text: "What legal issues arise when the chain of custody for electronic evidence is disputed?" },
      { title: "Constitutional argument", text: "Analyse Article 14 reasonable classification and identify adverse counterarguments." },
    ],
  },
  admin: {
    nav: "Legal research",
    workspace: "Administration",
    eyebrow: "Corpus administration research",
    heading: "Inspect grounded legal authority",
    description: "Run neutral, citation-controlled research across the verified global corpus.",
    placeholder: "Ask a focused legal research question…",
    badge: "Administrative research",
    suggestions: [
      { title: "Criminal procedure", text: "Is FIR registration mandatory for cognizable offences?" },
      { title: "Bail research", text: "What are the conditions for granting bail under CrPC?" },
      { title: "Constitutional law", text: "Explain the right to equality under Article 14." },
      { title: "Contract law", text: "What are the essential elements of a valid contract?" },
    ],
  },
} as const;

function newMessage(role: ChatMessage["role"], content: string): ChatMessage {
  return { id: crypto.randomUUID(), role, content, timestamp: Date.now() };
}

export default function HomePage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState<IngestionProgress | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [view, setView] = useState<"dashboard" | "research" | "workspace">("dashboard");
  const [mobileNav, setMobileNav] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);
  const [responseMode, setResponseMode] = useState<RequestedResponseMode>("auto");
  const experience = ROLE_EXPERIENCES[(user?.role as keyof typeof ROLE_EXPERIENCES) ?? "citizen"] ?? ROLE_EXPERIENCES.citizen;

  useEffect(() => {
    let mounted = true;
    const restoreAuth = async () => {
      try { const current = await getMe(); if (mounted) setUser(current); }
      catch { try { const current = await refreshSession(); if (mounted) setUser(current); } catch { if (mounted) setUser(null); } }
      finally { if (mounted) setAuthChecked(true); }
    };
    const poll = async () => { try { const next = await getIngestionProgress(); if (mounted) setProgress(next); } catch { if (mounted) setProgress(null); } };
    restoreAuth(); poll(); const interval = setInterval(poll, 30_000);
    return () => { mounted = false; clearInterval(interval); };
  }, []);

  const submit = async (query: string) => {
    if (!query.trim() || loading || !user) return;
    setView("research");
    const assistantId = crypto.randomUUID();
    const agentLabel = user.role === "police" ? "Police Procedure Research Agent" : user.role === "advocate" ? "Advocate Authority Research Agent" : "Citizen Legal Navigator";
    setMessages((current) => [...current, newMessage("user", query.trim()), { id: assistantId, role: "assistant", content: "", timestamp: Date.now(), loading: true, requestedMode: responseMode, agentLabel }]);
    setLoading(true);
    try {
      const response = await chatWithCorpus(query.trim(), sessionId, responseMode);
      setSessionId(response.session_id);
      setMessages((current) => current.map((message) => message.id === assistantId ? { ...message, content: response.answer, loading: false, citations: response.citations, confidenceScore: response.confidence_score, evidenceStrength: response.evidence_strength, responseMode: response.response_mode, requestedMode: response.requested_mode, routingReason: response.routing_reason, routingSignals: response.routing_signals, timingsMs: response.timings_ms, latencyTargetMs: response.latency_target_ms, targetMet: response.target_met } : message));
    } catch (error) {
      const detail = error instanceof ApiError ? error.message : "The legal corpus is unavailable. Confirm the backend is healthy and try again.";
      setMessages((current) => current.map((item) => item.id === assistantId ? { ...item, content: "", loading: false, error: detail } : item));
    } finally { setLoading(false); }
  };

  const signOut = async () => { await logout().catch(() => undefined); setUser(null); setMessages([]); setSessionId(null); };
  const hasProfessionalWorkspace = user?.role === "police" || user?.role === "advocate";
  const hasOperationsWorkspace = hasProfessionalWorkspace || user?.role === "admin";
  const resetResearch = () => { setMessages([]); setSessionId(null); setView("research"); };
  const navigate = (target: "dashboard" | "research" | "workspace") => { setView(target); setMobileNav(false); };

  useEffect(() => {
    const handleShortcut = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); setCommandOpen((open) => !open); return; }
      if (event.key === "Escape") { setCommandOpen(false); return; }
      const target = event.target as HTMLElement | null;
      if (target?.matches("input, textarea, select, [contenteditable='true']")) return;
      if (event.key.toLowerCase() === "d") navigate("dashboard");
      if (event.key.toLowerCase() === "r") navigate("research");
      if (event.key.toLowerCase() === "c" && hasOperationsWorkspace) navigate("workspace");
      if (event.key.toLowerCase() === "a" && hasProfessionalWorkspace) { navigate("workspace"); window.setTimeout(() => document.getElementById("document-analyzer")?.scrollIntoView({ behavior: "smooth", block: "start" }), 80); }
      if (event.key.toLowerCase() === "n") resetResearch();
    };
    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
  }, [hasOperationsWorkspace, hasProfessionalWorkspace]);

  const navButton = (target: "dashboard" | "research" | "workspace", label: string, icon: React.ReactNode, shortcut: string) => (
    <button onClick={() => { setView(target); setMobileNav(false); }} className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition ${view === target ? "bg-white/10 text-white" : "text-slate-400 hover:bg-white/5 hover:text-slate-200"}`}>
      {icon}<span>{label}</span>{view === target ? <ChevronRight size={15} className="ml-auto" /> : <kbd className="ml-auto text-[9px] font-medium text-slate-600">{shortcut}</kbd>}
    </button>
  );

  const viewLabel = view === "dashboard" ? "Command centre" : view === "research" ? experience.nav : experience.workspace;

  if (!authChecked) {
    return <main className="flex min-h-screen items-center justify-center bg-[#0b1729]"><div className="h-8 w-8 animate-spin rounded-full border-2 border-white/20 border-t-white" aria-label="Loading secure workspace" /></main>;
  }

  if (!user) {
    return <main className="min-h-screen"><AuthModal onSuccess={setUser} progress={progress} /></main>;
  }

  return (
    <main className="min-h-screen bg-[#f4f6f8] text-[#101828]">
      <DesktopReadiness />
      <aside className={`fixed inset-y-0 left-0 z-40 flex w-[258px] flex-col bg-[#0b1729] px-4 py-5 text-white transition-transform lg:translate-x-0 ${mobileNav ? "translate-x-0" : "-translate-x-full"}`}>
        <div className="flex items-center gap-3 px-2">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-white/10 bg-white/10"><Landmark size={20} /></div>
          <div><p className="text-sm font-semibold">Aegis Legal</p><p className="text-[10px] uppercase tracking-[0.18em] text-slate-500">Intelligence console</p></div>
        </div>
        <div className="mt-9 px-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-600">Workspace</div>
        <nav className="mt-2 space-y-1">
          {navButton("dashboard", "Command centre", <Gauge size={17} />, "D")}
          {navButton("research", experience.nav, <Search size={17} />, "R")}
          {hasOperationsWorkspace && navButton("workspace", experience.workspace, <BriefcaseBusiness size={17} />, "C")}
          {hasProfessionalWorkspace && <button onClick={() => { navigate("workspace"); window.setTimeout(() => document.getElementById("document-analyzer")?.scrollIntoView({ behavior: "smooth", block: "start" }), 80); }} className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-slate-400 transition hover:bg-white/5 hover:text-slate-200"><ScanSearch size={17} /><span>Document Analyzer</span><kbd className="ml-auto text-[9px] font-medium text-slate-600">A</kbd></button>}
        </nav>
        <button onClick={() => setCommandOpen(true)} className="mt-5 flex w-full items-center gap-3 rounded-xl border border-white/10 bg-white/[.035] px-3 py-2.5 text-left text-xs text-slate-400 transition hover:bg-white/[.07] hover:text-white"><Command size={15} /><span className="flex-1">Quick command</span><kbd className="rounded border border-white/10 px-1.5 py-0.5 text-[9px]">⌘K</kbd></button>
        <div className="mt-8 px-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-600">System</div>
        <div className="mt-2 rounded-xl border border-white/10 bg-white/[0.035] p-3">
          <div className="flex items-center justify-between"><span className="text-xs font-medium text-slate-300">Global corpus</span><span className="flex items-center gap-1.5 text-[10px] font-medium text-[#72d1c9]"><span className="h-1.5 w-1.5 rounded-full bg-[#72d1c9]" />ONLINE</span></div>
          <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/10"><div className="h-full rounded-full bg-[#42a9b2]" style={{ width: `${progress?.percent ?? 0}%` }} /></div>
          <div className="mt-3 grid grid-cols-2 gap-2 text-xs"><div><p className="font-semibold text-white">{progress?.canonical_documents?.toLocaleString() ?? "—"}</p><p className="text-[10px] text-slate-500">Gold sources</p></div><div><p className="font-semibold text-white">{(progress?.global_points ?? progress?.qdrant_points)?.toLocaleString() ?? "—"}</p><p className="text-[10px] text-slate-500">Passages</p></div></div>
        </div>
        {user && <div className="mt-auto border-t border-white/10 pt-4"><div className="flex items-center gap-3 px-2"><div className="flex h-9 w-9 items-center justify-center rounded-full bg-[#1d344d] text-xs font-semibold">{user.name?.slice(0, 2).toUpperCase()}</div><div className="min-w-0 flex-1"><p className="truncate text-xs font-medium">{user.name}</p><p className="truncate text-[10px] capitalize text-slate-500">{user.role} access</p></div><button onClick={signOut} className="rounded-lg p-2 text-slate-500 hover:bg-white/5 hover:text-white" aria-label="Sign out"><LogOut size={16} /></button></div></div>}
      </aside>
      {mobileNav && <button aria-label="Close navigation" className="fixed inset-0 z-30 bg-[#0b1729]/50 lg:hidden" onClick={() => setMobileNav(false)} />}

      <div className="min-h-screen lg:pl-[258px]">
        <header className="sticky top-0 z-20 flex h-[70px] items-center justify-between border-b border-[#e4e7ec] bg-white/95 px-5 backdrop-blur md:px-8">
          <div className="flex items-center gap-3"><button aria-label="Open navigation" onClick={() => setMobileNav(true)} className="rounded-lg border border-[#e4e7ec] p-2 lg:hidden"><Menu size={18} /></button><div><p className="text-xs text-[#667085]">Workspace / <span className="text-[#344054]">{viewLabel}</span></p><h1 className="mt-0.5 text-sm font-semibold">{view === "dashboard" ? `${experience.badge} command centre` : view === "research" ? "Global Legal Corpus" : experience.workspace}</h1></div></div>
          <div className="flex items-center gap-2 sm:gap-3"><button onClick={() => setCommandOpen(true)} className="hidden items-center gap-2 rounded-xl border border-[#e4e7ec] bg-white px-3 py-2 text-xs font-medium text-[#667085] shadow-sm hover:bg-[#f9fafb] md:flex"><Search size={14} />Search commands <kbd className="ml-2 rounded border border-[#d0d5dd] px-1.5 py-0.5 text-[9px]">⌘K</kbd></button><div className="hidden items-center gap-2 rounded-full border border-[#d7eadf] bg-[#f1faf5] px-3 py-1.5 text-xs font-medium text-[#16734a] sm:flex"><ShieldCheck size={14} />Private deployment</div>{user && <div className="flex h-9 w-9 items-center justify-center rounded-full border border-[#d0d5dd] bg-white text-[#475467]"><UserRound size={17} /></div>}</div>
        </header>

        {view === "dashboard" && user ? <RoleDashboard user={user} progress={progress} onNavigate={navigate} onResearch={submit} /> : view === "workspace" && user?.role === "admin" ? <AdminWorkspace /> : view === "workspace" && user && hasProfessionalWorkspace ? <ProfessionalWorkspace user={user} /> : (
          <section className="mx-auto flex min-h-[calc(100vh-70px)] max-w-[1180px] flex-col px-5 py-7 md:px-8 md:py-9">
            {messages.length === 0 ? (
              <>
                <div className="flex flex-col justify-between gap-5 md:flex-row md:items-end">
                  <div><p className="eyebrow">{experience.eyebrow}</p><h2 className="mt-2 text-3xl font-semibold tracking-[-0.035em] text-[#101828] md:text-[38px]">{experience.heading}</h2><p className="mt-3 max-w-2xl text-sm leading-6 text-[#667085]">{experience.description}</p></div>
                  <div className="space-y-2 text-right"><div className="flex items-center justify-end gap-2 text-xs text-[#667085]"><CheckCircle2 size={16} className="text-[#16825d]" />Corpus validation passed</div><span className="inline-flex rounded-full bg-[#eef6f7] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-[#167184]">{experience.badge}</span></div>
                </div>

                <div className="panel mt-8 overflow-hidden">
                  <div className="border-b border-[#eaecf0] px-5 py-4"><div className="flex items-center justify-between"><div className="flex items-center gap-2 text-sm font-semibold"><BookOpenText size={17} className="text-[#167184]" />New research</div><span className="rounded-full bg-[#eef6f7] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-[#167184]">Citation controlled</span></div></div>
                  <div className="px-5 pb-2 pt-5"><ChatInput onSend={submit} loading={loading} disabled={!user} placeholder={user ? experience.placeholder : "Sign in to begin research"} mode={responseMode} onModeChange={setResponseMode} /></div>
                </div>

                <div className="mt-7 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                  {experience.suggestions.map((suggestion) => <button key={suggestion.text} onClick={() => submit(suggestion.text)} disabled={loading} className="group panel p-5 text-left transition hover:-translate-y-0.5 hover:border-[#a9cbd0] hover:shadow-[0_8px_25px_rgba(16,24,40,.07)] disabled:opacity-50"><span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#167184]">{suggestion.title}</span><p className="mt-3 text-sm font-medium leading-6 text-[#344054]">{suggestion.text}</p><ChevronRight size={16} className="mt-5 text-[#98a2b3] transition group-hover:translate-x-1 group-hover:text-[#167184]" /></button>)}
                </div>

                <div className="mt-7 grid gap-4 md:grid-cols-3">
                  <div className="panel flex items-center gap-4 p-5"><div className="flex h-11 w-11 items-center justify-center rounded-xl bg-[#eef6f7] text-[#167184]"><Database size={20} /></div><div><p className="text-xl font-semibold">{progress?.canonical_documents?.toLocaleString() ?? "—"}</p><p className="text-xs text-[#667085]">Canonical legal sources</p></div></div>
                  <div className="panel flex items-center gap-4 p-5"><div className="flex h-11 w-11 items-center justify-center rounded-xl bg-[#f0f3fa] text-[#365899]"><BookOpenText size={20} /></div><div><p className="text-xl font-semibold">{(progress?.global_points ?? progress?.qdrant_points)?.toLocaleString() ?? "—"}</p><p className="text-xs text-[#667085]">Searchable legal passages</p></div></div>
                  <div className="panel flex items-center gap-4 p-5"><div className="flex h-11 w-11 items-center justify-center rounded-xl bg-[#eef8f2] text-[#16825d]"><ShieldCheck size={20} /></div><div><p className="text-xl font-semibold">Verified</p><p className="text-xs text-[#667085]">Gold + governed extended</p></div></div>
                </div>
              </>
            ) : (
              <div className="mx-auto flex w-full max-w-[900px] flex-1 flex-col">
                <div className="mb-6 flex items-end justify-between"><div><p className="eyebrow">Research matter</p><h2 className="mt-1 text-2xl font-semibold tracking-tight">Grounded legal analysis</h2></div><button onClick={resetResearch} className="button-secondary">New research</button></div>
                <div className="space-y-4">{messages.map((message) => <MessageBubble key={message.id} message={message} />)}</div>
                <div className="sticky bottom-0 mt-auto bg-gradient-to-t from-[#f4f6f8] via-[#f4f6f8] to-transparent pt-8"><ChatInput onSend={submit} loading={loading} disabled={!user} mode={responseMode} onModeChange={setResponseMode} /></div>
              </div>
            )}
          </section>
        )}
      </div>
      {user && <CommandPalette open={commandOpen} user={user} onClose={() => setCommandOpen(false)} onNavigate={navigate} onResearch={submit} />}
    </main>
  );
}
