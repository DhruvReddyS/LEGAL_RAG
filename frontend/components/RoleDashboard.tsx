"use client";

import {
  ArrowRight, BadgeCheck, BookOpenCheck, Bot, BriefcaseBusiness, CheckCircle2, Database,
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
    accent: "var(--accent)",
    tint: "var(--hover)",
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
    accent: "var(--accent)",
    tint: "var(--hover)",
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
    accent: "var(--accent)",
    tint: "var(--hover)",
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
    accent: "var(--ink)",
    tint: "var(--hover)",
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

  const workflow = <ol className="workflow-rail">{profile.workflow.map((step, index) => <li key={step}><span>{String(index + 1).padStart(2, "0")}</span><div><p>{step}</p><small>{index === profile.workflow.length - 1 ? "Professional judgement remains essential" : "A guided step in your workflow"}</small></div></li>)}</ol>;
  const capabilities = <div className={user.role === "citizen" ? "citizen-capabilities" : "capability-list"}>{profile.agents.map(agent => <button key={agent.name} onClick={() => launchAgent(agent)} className="premium-card"><agent.icon size={21} /><div><h3>{agent.name.replace(" Agent", "")}</h3><p>{agent.detail}</p></div></button>)}</div>;
  const matterList = <div className="panel overflow-hidden"><div className="flex justify-between border-b border-[var(--border)] p-5"><h3 className="font-semibold">{user.role === "police" ? "Investigation register" : "Client matter folio"}</h3><span className="text-xs text-[var(--ink-soft)]">{cases.length} matter{cases.length === 1 ? "" : "s"}</span></div>{cases.length ? cases.slice(0, 4).map(item => <button key={item.id} onClick={() => onNavigate("workspace")} className="flex w-full items-center justify-between gap-3 border-b border-[var(--state-warn-bg)] p-5 text-left transition hover:bg-[var(--hover)]"><span className="min-w-0 truncate text-sm">{item.title}</span><span className="text-xs capitalize text-[var(--accent)]">{item.status}</span></button>) : <div className="p-7"><p className="display-type text-xl">A clear record starts here.</p><p className="mt-2 text-sm leading-6 text-[var(--ink-soft)]">Open a matter to organise documents, evidence and your working analysis.</p></div>}<button className="button-secondary m-5" onClick={() => onNavigate("workspace")}>Open {user.role === "police" ? "case operations" : "matter workspace"}</button></div>;
  return <section className={"role-home role-home-" + user.role}>
    <div className="mb-8 flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border)] pb-4 text-xs text-[var(--ink-soft)]"><p>{dateLabel}</p><p>Welcome, {firstName}</p></div>
    {user.role === "citizen" ? <>
      <div className="citizen-intro">
        <div><p className="eyebrow">Your legal starting point</p><h1>Understand your rights.<br /><em>Know your next step.</em></h1><p className="intro-copy">You do not need to speak the language of law to understand where you stand. Start with a question. We will help you find the authority behind the answer.</p><button onClick={() => onNavigate("research")} className="button-primary mt-7"><Search size={17} />Ask a legal question</button><p className="mt-4 text-xs text-[var(--ink-soft)]">Plain language. Traceable sources. Clear limitations.</p></div>
        <aside className="citizen-note"><BookOpenCheck size={28} /><p className="display-type mt-6 text-3xl leading-tight">An answer is only as useful as the evidence behind it.</p><p className="mt-5 text-sm leading-7">Open the cited passage, see the source, and understand what an answer does—and does not—establish.</p><div className="mt-8 border-t border-[var(--state-warn-line)] pt-5"><span className="display-type text-3xl">{progress?.canonical_documents?.toLocaleString() ?? "—"}</span><p className="mt-1 text-xs">Canonical authorities in the corpus</p></div></aside>
      </div>
      <h2 className="mb-5 mt-12 text-2xl">A little direction, when you need it.</h2>{capabilities}
      <p className="mt-7 flex items-start gap-2 text-xs leading-5 text-[var(--ink-soft)]"><ShieldCheck size={16} className="shrink-0" />Corpusil provides legal information. Important decisions should be reviewed with a qualified professional.</p>
    </> : user.role === "police" ? <>
      <div className="mb-8 flex flex-wrap items-end justify-between gap-5"><div><p className="eyebrow">Police operations desk</p><h1 className="mt-3 text-4xl leading-tight">Procedure first.<br />A defensible record follows.</h1></div><button className="button-primary" onClick={() => onNavigate("workspace")}><ClipboardCheck size={17} />Open investigation</button></div>
      <div className="police-desk"><aside className="operational-rail"><p className="mb-6 text-sm font-semibold">Investigation workflow</p>{workflow}<p className="mt-6 border-t border-white/15 pt-5 text-xs leading-6 text-[var(--state-warn-line)]">Private evidence is restricted to your authorised role and matter.</p></aside><div className="min-w-0 space-y-6">{matterList}<div><h2 className="mb-4 text-2xl">Procedure & evidence tools</h2>{capabilities}</div></div></div>
    </> : user.role === "advocate" ? <>
      <div className="advocate-heading"><p className="eyebrow">Counsel’s working desk</p><h1>Build the argument.<br /><em>Test every assumption.</em></h1><p className="intro-copy">A considered position starts with both sides: governing authority, disputed evidence and the strongest opposing case.</p></div>
      <div className="advocate-desk"><div className="drafting-feature"><Scale size={27} className="text-[var(--state-warn-line)]" /><h2 className="mt-6 text-3xl">The strategy brief</h2><p className="mt-4 max-w-md text-sm leading-7 text-[var(--paper)]/70">Bring allegations, facts and procedural history together. Develop a two-sided analysis before committing to a legal position.</p><div className="my-7 grid grid-cols-2 gap-5 border-y border-white/15 py-5 text-sm"><p>Supporting position<span className="mt-2 block text-xs text-[var(--paper)]/50">Evidence & governing authority</span></p><p>Opposing position<span className="mt-2 block text-xs text-[var(--paper)]/50">Challenges & distinctions</span></p></div><button onClick={() => onNavigate("workspace")} className="button-secondary"><Scale size={16} />Prepare a strategy brief</button></div>{matterList}</div>
      <h2 className="mb-4 mt-9 text-2xl">At the authority desk</h2>{capabilities}
    </> : <>
      <div className="mb-7 flex flex-wrap items-end justify-between gap-5"><div><p className="eyebrow">Corpus governance</p><h1 className="mt-3 text-4xl">Trust is an operational discipline.</h1><p className="intro-copy">Manage professional access, source quality and the publication trail.</p></div><button className="button-primary" onClick={() => onNavigate("workspace")}><Gauge size={16} />Open administration</button></div>
      <div className="admin-register"><div><Database size={22} /><strong>{progress?.canonical_documents?.toLocaleString() ?? "—"}</strong><span>Canonical sources</span></div><div><BookOpenCheck size={22} /><strong>{(progress?.global_points ?? progress?.qdrant_points)?.toLocaleString() ?? "—"}</strong><span>Indexed passages</span></div><div><ShieldCheck size={22} /><strong>{progress ? "Connected" : "Unavailable"}</strong><span>Corpus status endpoint</span></div></div>
      <div className="mt-8 grid gap-7 lg:grid-cols-[1.4fr_1fr]"><div><h2 className="mb-5 text-2xl">Management & inspection</h2>{capabilities}<div className="mt-6 border-l-2 border-[var(--state-warn-text)] py-2 pl-5 text-sm leading-7 text-[var(--ink-soft)]">Gold sources remain immutable. Extended sources move through staging, validation and publication. Review the queue and audit trail in administration.</div></div><div className="panel p-6"><h2 className="mb-6 text-2xl">Governance sequence</h2>{workflow}</div></div>
    </>}
  </section>;
}
