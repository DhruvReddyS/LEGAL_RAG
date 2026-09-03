"use client";

import { useState } from "react";
import BrandLogo from "@/components/BrandLogo";
import MessageBubble, { CorpusilThinking } from "@/components/MessageBubble";
import ChatInput from "@/components/ChatInput";
import { Badge } from "@/components/ui/badge";
import type { ChatMessage, RequestedResponseMode } from "@/lib/types";

const palette = [
  ["Forest", "#10201D", "Navigation & primary action"],
  ["Parchment", "#FAF3EB", "Brand field & warm surfaces"],
  ["Brass", "#785130", "Authority & emphasis"],
  ["Soft gold", "#D1AD77", "Accents on dark surfaces"],
  ["Ink", "#17211F", "Body text"],
  ["Sage", "#65716E", "Supporting text"],
];
const sample: ChatMessage = {
  id: "design-specimen", role: "assistant", timestamp: 0, responseMode: "deep",
  agentLabel: "Corpusil response specimen", evidenceStrength: "moderate", confidenceScore: .65,
  content: "## A clear answer, with its limits visible\nThis is **illustrative interface content**, not legal advice or a live research result. The same renderer is used in the research workspace.\n\n### Practical next steps\n1. Identify the issue and the information available.\n2. Open the cited passage and examine its context.\n3. Seek professional review before relying on a conclusion.\n\n> A source can support a specific proposition without resolving every aspect of a question.\n\n### What still needs review\n- Missing facts and conflicting accounts.\n- The source’s current status and applicability.\n\n```text\nMatter reference: [not supplied]\nAuthority review: pending\n```",
  citations: [{ number: 1, chunk_id: "illustrative-source", title: "Illustrative source — interface demonstration only", source_type: "reference", page_start: 12, page_end: 13, excerpt: "This sample passage demonstrates source expansion, passage copying and the evidence inspector. It is not an excerpt from a legal authority.", verification_status: "unverified", current_status: "status_unverified" }],
};

export default function DesignSystemPage() {
  const [mode, setMode] = useState<RequestedResponseMode>("auto");
  const [notice, setNotice] = useState("");
  return <main className="mx-auto max-w-[1160px] px-6 py-10 sm:px-10">
    <header className="flex flex-wrap items-center justify-between gap-6 border-b border-[#ded7cc] pb-7"><BrandLogo className="w-[320px]" /><div><p className="eyebrow">Interface reference</p><h1 className="mt-2 text-3xl">The Corpusil design language</h1><p className="mt-2 text-sm text-[#65716e]">Original artwork. Evidence-led interaction.</p></div></header>
    <section className="py-9"><h2 className="text-2xl">A palette drawn from the mark</h2><div className="mt-5 grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-6">{palette.map(([name, value, use]) => <div key={name}><div className="h-20 rounded-[10px_10px_10px_3px] border border-black/10" style={{ background: value }} /><h3 className="mt-3 text-sm font-semibold">{name}</h3><code className="text-xs text-[#65716e]">{value}</code><p className="mt-2 text-xs leading-5 text-[#65716e]">{use}</p></div>)}</div></section>
    <section className="grid gap-8 border-y border-[#ded7cc] py-8 md:grid-cols-2"><div><p className="eyebrow">Typography</p><h2 className="mt-4 text-4xl">Considered. Clear. Credible.</h2><p className="mt-4 max-w-[60ch] text-sm leading-7 text-[#65716e]">A literary serif for ideas and hierarchy. A quiet system sans-serif for reading, controls and evidence. No external font requests.</p></div><div><p className="eyebrow">Evidence states</p><div className="mt-5 flex flex-wrap gap-3"><Badge variant="strong">Strong evidence</Badge><Badge variant="moderate">Moderate evidence</Badge><Badge variant="insufficient">Insufficient evidence</Badge></div><p className="mt-4 text-xs leading-6 text-[#65716e]">State is always expressed in words, never by colour alone. Keyboard focus uses a brass ring; reduced-motion preferences stop decorative movement.</p></div></section>
    <section className="py-9"><h2 className="mb-5 text-2xl">A deliberate working state</h2><CorpusilThinking detail="Illustrative loading state — real research displays server-reported progress here." /></section>
    <section className="mx-auto max-w-[800px] border-t border-[#ded7cc] pt-8"><p className="eyebrow">Interactive response specimen</p><MessageBubble message={sample} onRegenerate={() => setNotice("Regeneration selected. This specimen does not send a research request.")} /><div className="mt-7"><ChatInput mode={mode} onModeChange={setMode} onSend={() => setNotice("Composer tested. This specimen does not send a research request.")} placeholder="Try the composer — no request will be sent…" /></div>{notice && <p role="status" className="mt-3 text-sm text-[#785130]">{notice}</p>}</section>
    <footer className="mt-12 border-t border-[#ded7cc] pt-6 text-xs text-[#65716e]">Design specimens only. <a href="/" className="ml-2 underline underline-offset-4">Return to the application</a></footer>
  </main>;
}
