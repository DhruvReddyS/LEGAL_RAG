"use client";

import {
  ArrowRight, BadgeCheck, BookOpenCheck, Bot, BriefcaseBusiness, CheckCircle2,
  ClipboardCheck, FileSearch, Fingerprint, Gauge, Landmark, LockKeyhole,
  Scale, Search, ShieldCheck, Sparkles, UploadCloud, UsersRound,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { listCases } from "@/lib/api";
import type { IngestionProgress, LegalCase, User } from "@/lib/types";

type AppView = "dashboard" | "research" | "workspace";

interface RoleDashboardProps {
  user: User;
  progress: IngestionProgress | null;
  onNavigate: (view: AppView) => void;
  onResearch: (query: string) => void;
}

const ROLE_DASHBOARD = {
  citizen: {
    eyebrow: "Citizen legal access",
    title: "Understand your rights. Know your next step.",
    description: "A guided legal information workspace that translates verified authority into understandable procedures without pretending to replace a lawyer.",
    accent: "#1f7a7f",
    tint: "#e9f7f5",
    icon: UsersRound,
    agents: [
      { name: "Procedure Navigator", detail: "Turns a legal issue into a clear sequence of practical steps.", icon: ClipboardCheck, query: "Explain how to report a cognizable offence and what information I should preserve." },
      { name: "Rights Explainer", detail: "Explains constitutional and statutory protections in plain language.", icon: ShieldCheck, query: "Explain Article 14 and its main limitations in plain language." },
      { name: "Authority Finder", detail: "Locates the exact Act, judgment or official guidance behind an answer.", icon: BookOpenCheck, query: "What official authorities establish when FIR registration is mandatory?" },
    ],
    workflow: ["Describe the issue", "Locate verified authority", "Review practical steps", "Escalate when needed"],
  },
  police: {
    eyebrow: "Police intelligence console",
    title: "Procedure-led investigation. Evidence you can defend.",
    description: "A controlled operational workspace for lawful investigation, evidence integrity, scoped case search and fact-faithful FIR review drafts.",
    accent: "#245b9e",
    tint: "#edf4ff",
    icon: Fingerprint,
    agents: [
      { name: "FIR Review Agent", detail: "Preserves uncertainty, flags missing fields and grounds provisions.", icon: ClipboardCheck, workspace: true },
      { name: "Evidence Integrity Agent", detail: "Surfaces chain-of-custody and authenticity safeguards.", icon: Fingerprint, query: "Analyse safeguards for authenticity and chain of custody of electronic evidence." },
      { name: "Procedure Compliance Agent", detail: "Checks arrest, search, seizure and recording duties.", icon: BadgeCheck, query: "What safeguards and documentation apply during arrest and search?" },
      { name: "Case Evidence Search", detail: "Searches verified public law plus only the selected police matter.", icon: FileSearch, workspace: true },
    ],
    workflow: ["Open investigation matter", "Index private evidence", "Check governing procedure", "Generate review draft"],
  },
  advocate: {
    eyebrow: "Advocate intelligence suite",
    title: "Build the argument. Test the opposition. Verify every authority.",
    description: "A private matter workspace for two-sided legal strategy, authority mapping, evidence challenges and citation-controlled research.",
    accent: "#76512f",
    tint: "#faf3e9",
    icon: Scale,
    agents: [
      { name: "Defence Strategy Agent", detail: "Builds lawful points, opposing arguments and verification status.", icon: Scale, workspace: true },
      { name: "Authority Mapper", detail: "Connects propositions to Acts, provisions and controlling decisions.", icon: Landmark, query: "Compare the governing authorities on mandatory FIR registration and identify adverse arguments." },
      { name: "Evidence Challenge Agent", detail: "Identifies admissibility, contradiction and proof weaknesses.", icon: Fingerprint, query: "Analyse legal issues when electronic evidence authenticity and chain of custody are disputed." },
      { name: "Precedent Comparator", detail: "Tests similarities, distinctions and hierarchy across decisions.", icon: BookOpenCheck, query: "Compare current Supreme Court authority on preliminary inquiry and mandatory FIR registration." },
    ],
    workflow: ["Open client matter", "Index authorised material", "Map issues and authority", "Run two-sided strategy"],
  },
  admin: {
    eyebrow: "Platform administration",
    title: "Govern the corpus. Inspect the evidence trail.",
    description: "System-level visibility for corpus operations and neutral citation-controlled legal research.",
    accent: "#4f5968",
    tint: "#f1f3f6",
    icon: Gauge,
    agents: [
      { name: "Corpus Inspector", detail: "Reviews staged sources, validation gates and publication provenance.", icon: BookOpenCheck, workspace: true },
      { name: "Audit Research", detail: "Runs neutral evidence-first legal research.", icon: Search, query: "Explain Article 14 using only indexed authorities." },
    ],
    workflow: ["Inspect health", "Review corpus", "Run grounded query", "Audit evidence trail"],
  },
} as const;

export default function RoleDashboard({ user, progress, onNavigate, onResearch }: RoleDashboardProps) {
  const profile = ROLE_DASHBOARD[(user.role as keyof typeof ROLE_DASHBOARD) ?? "citizen"] ?? ROLE_DASHBOARD.citizen;
  const [cases, setCases] = useState<LegalCase[]>([]);
  const professional = user.role === "police" || user.role === "advocate";
  const firstName = user.name.split(" ")[0];
  const dateLabel = useMemo(() => new Intl.DateTimeFormat("en-IN", { weekday: "long", day: "numeric", month: "long" }).format(new Date()), []);

  useEffect(() => {
    if (!professional) return;
    listCases().then((result) => setCases(result.cases)).catch(() => setCases([]));
  }, [professional]);

  const launchAgent = (agent: (typeof profile.agents)[number]) => {
    if ("workspace" in agent && agent.workspace) onNavigate("workspace");
    else if ("query" in agent && agent.query) onResearch(agent.query);
  };

  return (
    <section className="mx-auto max-w-[1480px] px-5 py-7 md:px-8 md:py-9">
      <div className="mb-7 flex flex-col justify-between gap-3 md:flex-row md:items-end">
        <div><p className="text-xs font-medium text-[#667085]">{dateLabel}</p><h2 className="mt-1 text-2xl font-semibold tracking-[-0.03em] md:text-[30px]">Welcome back, {firstName}</h2></div>
        <div className="flex items-center gap-2 text-xs text-[#667085]"><span className="h-2 w-2 rounded-full bg-[#20a36b] shadow-[0_0_0_4px_rgba(32,163,107,.1)]" />All intelligence services operational</div>
      </div>

      <div className="relative overflow-hidden rounded-[26px] bg-[#0a1729] px-6 py-7 text-white shadow-[0_20px_50px_rgba(11,23,41,.18)] md:px-9 md:py-9">
        <div className="absolute inset-0 opacity-30 [background-image:radial-gradient(circle_at_82%_18%,rgba(90,198,204,.35),transparent_24%),linear-gradient(120deg,transparent_45%,rgba(255,255,255,.04))]" />
        <div className="relative grid gap-8 lg:grid-cols-[minmax(0,1.35fr)_minmax(280px,.65fr)] lg:items-end">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[.06] px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[.18em] text-[#9ddbe0]"><profile.icon size={13} />{profile.eyebrow}</div>
            <h1 className="mt-5 max-w-4xl text-3xl font-semibold leading-[1.08] tracking-[-.04em] md:text-[44px]">{profile.title}</h1>
            <p className="mt-4 max-w-3xl text-sm leading-6 text-slate-300">{profile.description}</p>
            <div className="mt-7 flex flex-wrap gap-3"><button onClick={() => onNavigate("research")} className="inline-flex items-center gap-2 rounded-xl bg-white px-4 py-2.5 text-sm font-semibold text-[#0b1729] transition hover:bg-[#edf5f6]"><Sparkles size={16} />Start intelligent research</button>{(professional || user.role === "admin") && <button onClick={() => onNavigate("workspace")} className="inline-flex items-center gap-2 rounded-xl border border-white/15 bg-white/[.06] px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-white/10"><BriefcaseBusiness size={16} />{user.role === "admin" ? "Open administration" : "Open case operations"}</button>}</div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-2xl border border-white/10 bg-white/[.055] p-4 backdrop-blur"><p className="text-2xl font-semibold">{progress?.canonical_documents?.toLocaleString() ?? "—"}</p><p className="mt-1 text-[11px] text-slate-400">Canonical authorities</p></div>
            <div className="rounded-2xl border border-white/10 bg-white/[.055] p-4 backdrop-blur"><p className="text-2xl font-semibold">{progress?.global_points ? `${(progress.global_points / 1000).toFixed(1)}K` : progress?.qdrant_points ? `${(progress.qdrant_points / 1000).toFixed(1)}K` : "—"}</p><p className="mt-1 text-[11px] text-slate-400">Searchable passages</p></div>
            <div className="rounded-2xl border border-white/10 bg-white/[.055] p-4 backdrop-blur"><p className="text-2xl font-semibold">&lt;5s</p><p className="mt-1 text-[11px] text-slate-400">Fast research target</p></div>
            <div className="rounded-2xl border border-white/10 bg-white/[.055] p-4 backdrop-blur"><p className="text-2xl font-semibold">{professional ? cases.filter((item) => item.status === "open").length : "Gold"}</p><p className="mt-1 text-[11px] text-slate-400">{professional ? "Open private matters" : "Evidence quality"}</p></div>
          </div>
        </div>
      </div>

      <div className="mt-7 grid gap-6 xl:grid-cols-[minmax(0,1.5fr)_minmax(290px,.5fr)]">
        <div>
          <div className="mb-4 flex items-end justify-between"><div><p className="eyebrow">Your specialist agents</p><h3 className="mt-1.5 text-xl font-semibold tracking-tight">Purpose-built for {user.role === "citizen" ? "everyday legal needs" : `${user.role} work`}</h3></div><span className="hidden text-xs text-[#98a2b3] sm:block">Grounded · isolated · auditable</span></div>
          <div className="grid gap-4 md:grid-cols-2">
            {profile.agents.map((agent, index) => <button key={agent.name} onClick={() => launchAgent(agent)} className="group relative overflow-hidden rounded-2xl border border-[#e4e7ec] bg-white p-5 text-left shadow-[0_1px_2px_rgba(16,24,40,.03)] transition hover:-translate-y-0.5 hover:border-[#b8c9cf] hover:shadow-[0_12px_30px_rgba(16,24,40,.08)]"><div className="flex items-start justify-between"><div className="flex h-11 w-11 items-center justify-center rounded-xl" style={{ background: profile.tint, color: profile.accent }}><agent.icon size={20} /></div><span className="rounded-full bg-[#f6f8fa] px-2 py-1 text-[9px] font-semibold uppercase tracking-[.13em] text-[#667085]">Agent {String(index + 1).padStart(2, "0")}</span></div><h4 className="mt-5 text-sm font-semibold text-[#1d2939]">{agent.name}</h4><p className="mt-2 min-h-10 text-xs leading-5 text-[#667085]">{agent.detail}</p><div className="mt-5 flex items-center gap-1.5 text-xs font-semibold" style={{ color: profile.accent }}>Open capability <ArrowRight size={13} className="transition group-hover:translate-x-1" /></div></button>)}
          </div>
        </div>

        <div className="space-y-5">
          <div className="panel overflow-hidden">
            <div className="border-b border-[#eaecf0] px-5 py-4"><p className="text-sm font-semibold">Recommended workflow</p></div>
            <div className="p-5">{profile.workflow.map((step, index) => <div key={step} className="flex gap-3 pb-5 last:pb-0"><div className="flex flex-col items-center"><span className="flex h-7 w-7 items-center justify-center rounded-full text-[10px] font-semibold" style={{ background: profile.tint, color: profile.accent }}>{index + 1}</span>{index < profile.workflow.length - 1 && <span className="mt-1 h-full w-px bg-[#e4e7ec]" />}</div><div className="pt-1"><p className="text-xs font-medium text-[#344054]">{step}</p><p className="mt-1 text-[10px] text-[#98a2b3]">{index === profile.workflow.length - 1 ? "Human review required" : "Evidence trail preserved"}</p></div></div>)}</div>
          </div>
          <div className="rounded-2xl border border-[#dce8e2] bg-[#f5fbf7] p-5"><div className="flex items-start gap-3"><div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white text-[#16825d] shadow-sm"><LockKeyhole size={17} /></div><div><p className="text-sm font-semibold text-[#1d4936]">Privacy boundary active</p><p className="mt-1.5 text-xs leading-5 text-[#4e7161]">{professional ? "Private evidence is restricted to owned matters and your professional role collection." : user.role === "admin" ? "Administrative mutations require explicit permissions and every account or corpus operation is audit logged." : "Citizen research is restricted to the verified global legal corpus."}</p></div></div></div>
        </div>
      </div>
    </section>
  );
}
