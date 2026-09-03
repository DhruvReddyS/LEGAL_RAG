"use client";

import { Bot, BriefcaseBusiness, Gauge, ScanSearch, Search, Sparkles, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { User } from "@/lib/types";
import { useDialogFocus } from "@/components/useDialogFocus";

type AppView = "dashboard" | "research" | "workspace";

interface CommandPaletteProps {
  open: boolean;
  user: User;
  onClose: () => void;
  onNavigate: (view: AppView) => void;
  onResearch: (query: string) => void;
}

export default function CommandPalette({ open, user, onClose, onNavigate, onResearch }: CommandPaletteProps) {
  const [filter, setFilter] = useState("");
  const dialogRef = useDialogFocus(open, onClose);
  const professional = user.role === "police" || user.role === "advocate";
  const operations = professional || user.role === "admin";
  useEffect(() => { if (open) setFilter(""); }, [open]);
  const commands = useMemo(() => [
    { label: "Open command centre", detail: "Role dashboard and specialist agents", icon: Gauge, shortcut: "D", run: () => onNavigate("dashboard") },
    { label: "Start legal research", detail: "Auto-route a grounded legal question", icon: Search, shortcut: "R", run: () => onNavigate("research") },
    ...(operations ? [{ label: user.role === "police" ? "Open police case operations" : user.role === "advocate" ? "Open advocate matter strategy" : "Open administration workspace", detail: user.role === "admin" ? "Accounts, corpus governance and audit events" : "Private cases, evidence and professional agents", icon: BriefcaseBusiness, shortcut: "C", run: () => onNavigate("workspace" as AppView) }] : []),
    ...(professional ? [{ label: "Open Document Analyzer", detail: "Review indexed evidence, clauses, risks and verified authority", icon: ScanSearch, shortcut: "A", run: () => { onNavigate("workspace" as AppView); window.setTimeout(() => document.getElementById("document-analyzer")?.scrollIntoView({ behavior: "smooth", block: "start" }), 80); } }] : []),
    { label: "Test mandatory FIR authority", detail: "Run a known grounded research scenario", icon: Sparkles, run: () => onResearch("Is FIR registration mandatory for cognizable offences? State only what retrieved authorities establish.") },
    { label: user.role === "advocate" ? "Run two-sided authority review" : user.role === "police" ? "Check electronic evidence safeguards" : "Explain a right in plain language", detail: "Launch the recommended role-specific agent", icon: Bot, run: () => onResearch(user.role === "advocate" ? "Analyse the strongest lawful arguments on both sides of a bail application." : user.role === "police" ? "Analyse safeguards for electronic evidence authenticity and chain of custody." : "Explain Article 14 and its main limitations in plain language.") },
  ], [operations, professional, user.role, onNavigate, onResearch]);
  const shown = commands.filter((item) => `${item.label} ${item.detail}`.toLowerCase().includes(filter.toLowerCase()));
  if (!open) return null;
  return <div className="fixed inset-0 z-[80] flex items-start justify-center bg-[#10201d]/55 px-4 pt-[12vh] backdrop-blur-sm" onMouseDown={onClose}><div ref={dialogRef} role="dialog" aria-modal="true" aria-label="Command palette" onMouseDown={(event) => event.stopPropagation()} className="w-full max-w-2xl overflow-hidden rounded-2xl border border-white/20 bg-white shadow-[0_30px_80px_rgba(5,15,30,.35)]"><div className="flex items-center gap-3 border-b border-[#e7e0d6] px-5"><Search size={18} className="text-[#65716e]" /><input autoFocus value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="Search commands, agents and workflows…" aria-label="Search commands" className="h-16 min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-[#75817b]" /><button onClick={onClose} aria-label="Close command palette" className="rounded-lg p-2 text-[#75817b] hover:bg-[#f1eee8]"><X size={17} /></button></div><div className="max-h-[430px] overflow-auto p-2"><p className="px-3 pb-2 pt-2 text-[10px] font-semibold text-[#75817b]">Available commands</p>{shown.map((item) => <button key={item.label} onClick={() => { item.run(); onClose(); }} className="group flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left hover:bg-[#faf3eb]"><span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#f1e7dc] text-[#785130]"><item.icon size={18} /></span><span className="min-w-0 flex-1"><span className="block text-sm font-medium text-[#35413e]">{item.label}</span><span className="mt-0.5 block truncate text-xs text-[#75817b]">{item.detail}</span></span>{item.shortcut && <kbd className="rounded-md border border-[#cbc4b9] bg-white px-2 py-1 text-[10px] font-medium text-[#65716e] shadow-sm">{item.shortcut}</kbd>}</button>)}{!shown.length && <div className="px-4 py-12 text-center text-sm text-[#75817b]">No matching command</div>}</div><div className="flex items-center justify-between border-t border-[#e7e0d6] bg-[#fafbfc] px-5 py-3 text-[10px] text-[#75817b]"><span>Role scope: <strong className="capitalize text-[#65716e]">{user.role}</strong></span><span>Esc to close / ⌘K to toggle</span></div></div></div>;
}
