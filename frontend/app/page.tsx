"use client";

import { ArrowDown, BookOpenText, BriefcaseBusiness, Check, FilePenLine, Fingerprint, HelpCircle, History, LogOut, Menu, MessageSquare, MoreHorizontal, Pencil, Pin, PinOff, Plus, Scale, ScanSearch, Settings, ShieldCheck, Trash2, Undo2, X, Zap } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import AuthModal from "@/components/AuthModal";
import BrandLogo from "@/components/BrandLogo";
import ChatInput from "@/components/ChatInput";
import MessageBubble from "@/components/MessageBubble";
import CitizenGuideDialog from "@/components/CitizenGuideDialog";
import UploadPrivacy from "@/components/UploadPrivacy";
import { legalCategory } from "@/lib/answer-presentation";
import ProfessionalWorkspace from "@/components/ProfessionalWorkspace";
import { useDialogFocus } from "@/components/useDialogFocus";
import AdminWorkspace from "@/components/AdminWorkspace";
import DesktopReadiness from "@/components/DesktopReadiness";
import { ApiError, cancelDeepReviewJob, chatWithCorpus, getChatSession, getDeepReviewJob, getIngestionProgress, getMe, listChatSessions, logout, refreshSession } from "@/lib/api";
import type { ChatMessage, CitizenDocument, IngestionProgress, RequestedResponseMode, User } from "@/lib/types";

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

type SavedChat = {
  id: string;
  title: string;
  /** Empty until the row is opened; bodies load on demand. */
  messages: ChatMessage[];
  sessionId: string | null;
  updatedAt?: number;
  pinned?: boolean;
  customTitle?: boolean;
  preview?: string;
  messageCount?: number;
};

export default function HomePage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState<IngestionProgress | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const [draftVersion, setDraftVersion] = useState(0);
  const [view, setView] = useState<"research" | "workspace">("research");
  const [mobileNav, setMobileNav] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [guideOpen, setGuideOpen] = useState(false);
  const [citizenGuideSlide, setCitizenGuideSlide] = useState<number | null>(null);
  const [animate, setAnimate] = useState(true);
  const [theme, setTheme] = useState<"paper" | "ink">("paper");
  useEffect(() => { document.documentElement.dataset.theme = theme; }, [theme]);
  const [rememberHistory, setRememberHistory] = useState(true);
  const [history, setHistory] = useState<SavedChat[]>([]);
  const [historyReady, setHistoryReady] = useState(false);
  const [chatMenuId, setChatMenuId] = useState<string | null>(null);
  const [renamingChatId, setRenamingChatId] = useState<string | null>(null);
  const [renameDraft, setRenameDraft] = useState("");
  const [deletedChat, setDeletedChat] = useState<SavedChat | null>(null);
  const [historyNotice, setHistoryNotice] = useState("");
  const closeSettings = () => setSettingsOpen(false);
  const closeGuide = () => setGuideOpen(false);
  const settingsRef = useDialogFocus(settingsOpen, closeSettings);
  const guideRef = useDialogFocus(guideOpen, closeGuide);
  const [responseMode, setResponseMode] = useState<RequestedResponseMode>("auto");
  const [compactNavigation, setCompactNavigation] = useState(false);
  const latestMessage = useRef<HTMLDivElement>(null);
  const activeRequest = useRef<{ controller: AbortController; assistantId: string; jobId?: string } | null>(null);
  const [awayFromLatest, setAwayFromLatest] = useState(false);
  useEffect(() => {
    const check = () => setAwayFromLatest(document.documentElement.scrollHeight - window.innerHeight - window.scrollY > 280);
    window.addEventListener("scroll", check, { passive: true });
    return () => { window.removeEventListener("scroll", check); activeRequest.current?.controller.abort(); };
  }, []);
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

  useEffect(() => {
    const media = window.matchMedia("(max-width: 1023px)");
    const update = () => setCompactNavigation(media.matches);
    update(); media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (messages.length) latestMessage.current?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" });
  }, [messages.length]);

  useEffect(() => {
    if (!user) { setHistory([]); setHistoryReady(false); return; }
    // Preferences are per-device and stay local. Conversations do not: every
    // message is already persisted in PostgreSQL, and reading history from
    // sessionStorage meant it vanished when the tab closed and never appeared
    // on a second device.
    try {
      const preferences = JSON.parse(sessionStorage.getItem("corpusil-preferences:" + user.id) || "{}");
      setAnimate(preferences.animate !== false);
      setTheme(preferences.theme === "ink" ? "ink" : "paper");
      setRememberHistory(preferences.rememberHistory !== false);
      if (["auto", "fast", "deep"].includes(preferences.mode)) setResponseMode(preferences.mode);
    } catch { /* Storage disabled: fall back to defaults. */ }

    let cancelled = false;
    void (async () => {
      try {
        const stored = await listChatSessions(30);
        if (cancelled) return;
        setHistory(stored.items.map(item => ({
          id: item.id,
          title: item.title,
          // Bodies load on demand; a sidebar must not fetch every message of
          // every conversation, which for a case session includes evidence.
          messages: [],
          sessionId: item.id,
          updatedAt: Date.parse(item.updated_at),
          preview: item.last_message_preview ?? undefined,
          messageCount: item.message_count,
        })));
      } catch {
        // An offline or unauthenticated read must not blank the console.
        if (!cancelled) setHistory([]);
      } finally {
        if (!cancelled) setHistoryReady(true);
      }
    })();
    return () => { cancelled = true; };
  }, [user]);

  useEffect(() => {
    if (!user || !historyReady || loading || !activeChatId || !messages.length) return;
    // Keep the sidebar in step with the live conversation. The server already
    // holds the durable copy; this only avoids a round-trip after each answer.
    setHistory(current => {
      const existing = current.find(item => item.id === activeChatId || item.sessionId === sessionId);
      const savedChat: SavedChat = {
        id: existing?.id ?? activeChatId,
        title: existing?.customTitle ? existing.title : messages.find(message => message.role === "user")?.content.slice(0, 90) || "Untitled chat",
        messages,
        sessionId,
        updatedAt: Date.now(),
        pinned: existing?.pinned,
        customTitle: existing?.customTitle,
        messageCount: messages.length,
      };
      return [savedChat, ...current.filter(item => item !== existing)].slice(0, 30);
    });
  }, [messages, sessionId, loading, user, historyReady, activeChatId]);

  useEffect(() => {
    if (!user || !historyReady) return;
    try {
      sessionStorage.setItem("corpusil-preferences:" + user.id, JSON.stringify({ animate, rememberHistory, mode: responseMode, theme }));
      // Conversations are never mirrored into browser storage any more.
      sessionStorage.removeItem("corpusil-chats:" + user.id);
    } catch { /* Browsers with storage disabled keep history in memory. */ }
  }, [history, user, historyReady, rememberHistory, animate, responseMode, theme]);

  const stopResearch = () => {
    const active = activeRequest.current;
    if (!active) return;
    active.controller.abort(); activeRequest.current = null;
    setLoading(false);
    setMessages(current => current.map(message => message.id === active.assistantId ? { ...message, loading: false, stopped: true, content: "Response stopped." } : message));
    if (active.jobId) void cancelDeepReviewJob(active.jobId).catch(() => {
      setMessages(current => current.map(message => message.id === active.assistantId ? { ...message, content: "Stopped here. The server could not confirm cancellation and may finish the queued review." } : message));
    });
  };

  const submit = async (query: string, documents: CitizenDocument[] = [], regenerate = false, editIndex?: number) => {
    if (!query.trim() || loading || !user) return;
    const requestStarted = performance.now();
    setView("research");
    const assistantId = crypto.randomUUID();
    const operation = { controller: new AbortController(), assistantId, jobId: undefined as string | undefined };
    activeRequest.current = operation;
    const branchIndex = editIndex ?? (regenerate ? messages.map(message => message.role).lastIndexOf("user") : -1);
    if (branchIndex >= 0 || !activeChatId) setActiveChatId(crypto.randomUUID());
    const baseMessages = branchIndex >= 0 ? messages.slice(0, branchIndex) : messages;
    const priorMessages = branchIndex >= 0 ? baseMessages.filter(message => !message.error && !message.stopped && message.content.trim()).slice(-8).map(message => ({ role: message.role, content: message.content.slice(0, 4000) })) : [];
    const targetSession = branchIndex >= 0 ? null : sessionId;
    if (branchIndex >= 0) setSessionId(null);
    const agentLabel = user.role === "police" ? "Police Procedure Research Agent" : user.role === "advocate" ? "Advocate Authority Research Agent" : "Citizen Legal Navigator";
    const availableDocuments = documents.filter(document => document.pages.length > 0);
    setMessages([...baseMessages, { ...newMessage("user", query.trim()), documents: availableDocuments }, { id: assistantId, role: "assistant", content: "", timestamp: Date.now(), loading: true, requestedMode: availableDocuments.length ? "deep" : responseMode, agentLabel, documents: availableDocuments, category: legalCategory(query) }]);
    setLoading(true);
    try {
      const response = await chatWithCorpus(query.trim(), targetSession, availableDocuments.length ? "deep" : responseMode, availableDocuments, operation.controller.signal, priorMessages);
      if (operation.controller.signal.aborted) return;
      setSessionId(response.session_id);
      if (response.delivery_state === "searching_more_thoroughly" && response.job_id) {
        operation.jobId = response.job_id;
        setMessages((current) => current.map((message) => message.id === assistantId ? {
          ...message,
          content: response.answer,
          loading: true,
          responseMode: "deep",
          requestedMode: response.requested_mode,
          routingReason: response.routing_reason,
          routingSignals: response.routing_signals,
          citations: response.citations,
          provisional: response.citations.length > 0,
          stageLabel: null,
          jobProgress: 0,
        } : message));
        while (true) {
          await new Promise((resolve) => window.setTimeout(resolve, 1000));
          if (operation.controller.signal.aborted) return;
          const job = await getDeepReviewJob(response.job_id, operation.controller.signal);
          if (operation.controller.signal.aborted) return;
          setMessages((current) => current.map((message) => message.id === assistantId ? {
            ...message,
            loading: true,
            stageLabel: job.stage_label ?? null,
            jobProgress: job.progress,
          } : message));
          if (job.status === "succeeded" && job.result) {
            const result = job.result;
            setMessages((current) => current.map((message) => message.id === assistantId ? {
              ...message,
              content: result.answer,
              loading: false,
              citations: result.citations,
              confidenceScore: result.confidence_score,
              evidenceStrength: result.evidence_strength,
              responseMode: "deep",
              requestedMode: response.requested_mode,
              routingReason: response.routing_reason,
              routingSignals: response.routing_signals,
              timingsMs: result.timings_ms,
              pipelineMetrics: result.pipeline_metrics,
              latencyTargetMs: response.latency_target_ms,
              targetMet: null,
              provisional: false,
              stageLabel: null,
              jobProgress: null,
              clientElapsedMs: Math.round(performance.now() - requestStarted),
            } : message));
            break;
          }
          if (job.status === "failed" || job.status === "cancelled") {
            throw new ApiError(job.error_message || `Deep Review ${job.status}.`, 500);
          }
        }
        return;
      }
      setMessages((current) => current.map((message) => message.id === assistantId ? { ...message, content: response.answer, loading: false, citations: response.citations, confidenceScore: response.confidence_score, evidenceStrength: response.evidence_strength, responseMode: response.response_mode, requestedMode: response.requested_mode, routingReason: response.routing_reason, routingSignals: response.routing_signals, timingsMs: response.timings_ms, pipelineMetrics: response.pipeline_metrics, latencyTargetMs: response.latency_target_ms, targetMet: response.target_met, clientElapsedMs: Math.round(performance.now() - requestStarted) } : message));
    } catch (error) {
      if (operation.controller.signal.aborted) return;
      const detail = error instanceof ApiError ? error.message : "The legal corpus is unavailable. Confirm the backend is healthy and try again.";
      setMessages((current) => current.map((item) => item.id === assistantId ? { ...item, content: "", loading: false, error: detail } : item));
    } finally { if (activeRequest.current === operation) { activeRequest.current = null; setLoading(false); } }
  };

  const signOut = async () => { await logout().catch(() => undefined); setUser(null); setMessages([]); setSessionId(null); setActiveChatId(null); setView("research"); setResponseMode("auto"); setMobileNav(false); };
  const hasProfessionalWorkspace = user?.role === "police" || user?.role === "advocate";
  const hasOperationsWorkspace = hasProfessionalWorkspace || user?.role === "admin";
  const resetResearch = () => { setMessages([]); setSessionId(null); setActiveChatId(crypto.randomUUID()); setDraftVersion(value => value + 1); setView("research"); window.scrollTo({ top: 0, behavior: "auto" }); };
  const openSavedChat = (item: SavedChat) => {
    setChatMenuId(null);
    setActiveChatId(item.id);
    setSessionId(item.sessionId);
    setDraftVersion(value => value + 1);
    setView("research");
    setMobileNav(false);
    window.scrollTo({ top: 0, behavior: "auto" });

    if (item.messages.length || !item.sessionId) { setMessages(item.messages); return; }
    // Sidebar rows carry no bodies. Load this conversation's messages from the
    // server, with their stored citations and confidence scores intact.
    setMessages([{ id: crypto.randomUUID(), role: "assistant", content: "", timestamp: Date.now(), loading: true, requestedMode: "fast" }]);
    void (async () => {
      try {
        const stored = await getChatSession(item.sessionId!);
        const restored: ChatMessage[] = stored.messages.map(message => ({
          id: message.id,
          role: message.role === "user" ? "user" : "assistant",
          content: message.content,
          citations: message.citations,
          confidenceScore: message.confidence_score ?? undefined,
          timestamp: Date.parse(message.created_at),
        }));
        setMessages(restored);
        setHistory(current => current.map(row => row.id === item.id ? { ...row, messages: restored } : row));
      } catch {
        setMessages([{ id: crypto.randomUUID(), role: "assistant", content: "", timestamp: Date.now(), error: "This conversation could not be loaded. Check your connection and try again." }]);
      }
    })();
  };
  const togglePinned = (item: SavedChat) => {
    if (!item.pinned && history.filter(chat => chat.pinned).length >= 5) {
      setHistoryNotice("You can pin up to 5 chats. Unpin one to add another.");
      setChatMenuId(null);
      return;
    }
    setHistory(current => current.map(chat => chat.id === item.id ? { ...chat, pinned: !chat.pinned } : chat));
    setHistoryNotice(item.pinned ? "Chat moved back to recent." : "Chat pinned for quick access.");
    setChatMenuId(null);
  };
  const saveChatTitle = (item: SavedChat) => {
    const title = renameDraft.trim().slice(0, 90);
    if (title) setHistory(current => current.map(chat => chat.id === item.id ? { ...chat, title, customTitle: true } : chat));
    setRenamingChatId(null);
    setChatMenuId(null);
  };
  const deleteChat = (item: SavedChat) => {
    setDeletedChat(item);
    setHistory(current => current.filter(chat => chat.id !== item.id));
    setChatMenuId(null);
    setHistoryNotice("Chat deleted.");
    if (activeChatId === item.id) resetResearch();
  };
  const openTool = (id?: string) => {
    setView("workspace"); setMobileNav(false);
    if (id) window.setTimeout(() => document.getElementById(id)?.scrollIntoView({ behavior: animate ? "smooth" : "auto", block: "start" }), 80);
  };
  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => { if (event.key === "Escape") { setMobileNav(false); setSettingsOpen(false); setGuideOpen(false); setChatMenuId(null); setRenamingChatId(null); } };
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, []);

  if (!authChecked) return <main className="grid min-h-screen place-items-center"><Scale size={24} className="text-neutral-400" aria-label="Loading workspace" /></main>;
  if (!user) return <AuthModal onSuccess={setUser} progress={progress} />;

  const role = user.role;
  const tools = role === "citizen" ? [
    { title: "Know your rights", icon: ShieldCheck, guideIndex: 0 },
    { title: "Report an incident", icon: FilePenLine, guideIndex: 1 },
    { title: "Understand a document", icon: BookOpenText, guideIndex: 2 },
  ] : role === "police" ? [
    { title: "Investigations", icon: Fingerprint, target: "" },
    { title: "FIR drafting", icon: FilePenLine, target: "role-agent-tool" },
    { title: "Evidence & documents", icon: ScanSearch, target: "document-analyzer" },
  ] : role === "advocate" ? [
    { title: "Client matters", icon: BriefcaseBusiness, target: "" },
    { title: "Build a strategy", icon: Scale, target: "role-agent-tool" },
    { title: "Review documents", icon: ScanSearch, target: "document-analyzer" },
  ] : [{ title: "Manage workspace", icon: Settings, target: "" }];
  const pinnedChats = history.filter(item => item.pinned).sort((a, b) => (b.updatedAt ?? 0) - (a.updatedAt ?? 0));
  const recentChats = history.filter(item => !item.pinned).sort((a, b) => (b.updatedAt ?? 0) - (a.updatedAt ?? 0));
  const chatRow = (item: SavedChat) => <div className={`chat-history-row ${item.id === activeChatId ? "selected" : ""}`} key={item.id}>
    {renamingChatId === item.id ? <form className="chat-rename" onSubmit={event => { event.preventDefault(); saveChatTitle(item); }}><input autoFocus aria-label="Rename chat" value={renameDraft} maxLength={90} onChange={event => setRenameDraft(event.target.value)} onKeyDown={event => { if (event.key === "Escape") setRenamingChatId(null); }}/><button aria-label="Save chat name" disabled={!renameDraft.trim()}><Check size={13}/></button></form> : <button disabled={loading} className="chat-open" aria-current={item.id === activeChatId ? "page" : undefined} title={item.title} onClick={() => openSavedChat(item)}>{item.pinned ? <Pin size={13}/> : <MessageSquare size={14}/>}<span>{item.title}</span></button>}
    {renamingChatId !== item.id && <button className="chat-menu-trigger" aria-label={`Chat options for ${item.title}`} aria-expanded={chatMenuId === item.id} onClick={() => setChatMenuId(current => current === item.id ? null : item.id)}><MoreHorizontal size={15}/></button>}
    {chatMenuId === item.id && <div className="chat-menu" role="menu"><button role="menuitem" onClick={() => togglePinned(item)}>{item.pinned ? <PinOff size={14}/> : <Pin size={14}/>} {item.pinned ? "Unpin" : "Pin chat"}</button><button role="menuitem" onClick={() => { setRenamingChatId(item.id); setRenameDraft(item.title); setChatMenuId(null); }}><Pencil size={14}/>Rename</button><button role="menuitem" className="is-danger" onClick={() => deleteChat(item)}><Trash2 size={14}/>Delete</button></div>}
  </div>;

  return <main data-role={role} data-motion={animate ? "on" : "off"} className="app-shell">
    <aside aria-label="Main navigation" aria-hidden={compactNavigation && !mobileNav} ref={node => { if(node) node.inert = compactNavigation && !mobileNav; }} className={`app-sidebar ${mobileNav ? "is-open" : ""}`}>
      <div className="sidebar-brand"><BrandLogo /><button className="icon-button lg:hidden" onClick={() => setMobileNav(false)} aria-label="Close navigation"><X size={18} /></button></div>
      <button disabled={loading} className="new-chat-button" onClick={() => { resetResearch(); setMobileNav(false); }}><Plus size={18} />New chat</button>
      <nav className="feature-nav" aria-label="Features">{tools.map(tool => <button key={tool.title} onClick={() => { if ("guideIndex" in tool) { setCitizenGuideSlide(tool.guideIndex); setMobileNav(false); } else openTool(tool.target); }}><tool.icon size={18} strokeWidth={1.65} /><span>{tool.title}</span></button>)}</nav>
      <div className="chat-history">{pinnedChats.length > 0 && <><div className="history-heading"><span>Pinned <b>{pinnedChats.length}/5</b></span><Pin size={13}/></div>{pinnedChats.map(chatRow)}</>}<div className="history-heading"><span>Recent chats</span><History size={14}/></div>{recentChats.length ? recentChats.map(chatRow) : !pinnedChats.length && <p>Your conversations will appear here.</p>}</div>
      <div className="sidebar-bottom"><button onClick={() => { setMobileNav(false); role === "citizen" ? setCitizenGuideSlide(0) : setGuideOpen(true); }}><HelpCircle size={17} />Getting started</button><button onClick={() => { setMobileNav(false); setSettingsOpen(true); }}><Settings size={17} />Settings<span className="ml-auto text-[11px] capitalize text-neutral-400">{role}</span></button></div>
    </aside>
    {mobileNav && <button aria-label="Dismiss navigation" className="sidebar-scrim" onClick={() => setMobileNav(false)} />}
    {historyNotice && <div className="history-toast" role="status"><span>{historyNotice}</span>{deletedChat && historyNotice === "Chat deleted." && <button onClick={() => { setHistory(current => [deletedChat, ...current.filter(item => item.id !== deletedChat.id)].slice(0, 20)); setDeletedChat(null); setHistoryNotice("Chat restored."); }}><Undo2 size={13}/>Undo</button>}<button aria-label="Dismiss notification" onClick={() => { setHistoryNotice(""); setDeletedChat(null); }}><X size={13}/></button></div>}
    <div className="app-content" ref={node => { if(node) node.inert = compactNavigation && mobileNav; }}>
      <header className="workspace-header"><button className="icon-button lg:hidden" aria-label="Open navigation" onClick={() => setMobileNav(true)}><Menu size={20} /></button><span>{view === "workspace" ? role === "police" ? "Investigation workspace" : role === "advocate" ? "Your matter workspace" : "Administration" : " "}</span>{view === "workspace" && <button className="text-sm text-neutral-500" onClick={() => setView("research")}><MessageSquare size={16} className="mr-2 inline" />Back to chat</button>}</header>
      {view === "workspace" && hasOperationsWorkspace ? role === "admin" ? <AdminWorkspace /> : <ProfessionalWorkspace user={user} /> :
      <section className={`chat-workspace ${messages.length ? "has-conversation" : ""}`}>
        {!messages.length ? <div className="chat-welcome">
          <div className="welcome-symbol"><Scale size={32} strokeWidth={1.3} /></div>
          <h1>{role === "citizen" ? "Let’s make sense of the law." : role === "police" ? "What are you investigating?" : role === "advocate" ? "Where does your argument begin?" : "What would you like to research?"}</h1>
          <p>{role === "citizen" ? "Ask in your own words. We’ll start from there." : role === "police" ? "Explore procedure, preserve evidence, and build your record." : role === "advocate" ? "Find authority. Explore both sides. Refine your position." : "Explore your legal corpus."}</p>
          <ChatInput key={`${sessionId}:${draftVersion}`} onSend={submit} onStop={stopResearch} loading={loading} mode={responseMode} onModeChange={setResponseMode} placeholder={experience.placeholder} />
          <div className="prompt-shortcuts">{experience.suggestions.map((suggestion,index) => { const Icon = [FilePenLine, ScanSearch, ShieldCheck, BookOpenText][index]; return <button key={suggestion.title} disabled={loading} onClick={() => void submit(suggestion.text)}><Icon size={16} strokeWidth={1.6} />{suggestion.title}</button>; })}</div>
          <button className="guide-invite" onClick={() => role === "citizen" ? setCitizenGuideSlide(0) : setGuideOpen(true)}><HelpCircle size={14} />First time here? Take a quick look</button>
        </div> : <>
          <div className="conversation">{messages.map((message,index) => <div key={message.id} ref={index === messages.length-1 ? latestMessage : undefined}><MessageBubble message={message} onEdit={!loading && !message.documents?.some(document => !document.pages.length) ? (text) => void submit(text, message.documents, false, index) : undefined} onForgetDocuments={() => { const ids = new Set(message.documents?.map(document => document.id)); const clear = (items: ChatMessage[]) => items.map(item => ({...item, documents: item.documents?.map(document => ids.has(document.id) ? {...document, pages: []} : document)})); setMessages(clear); setHistory(current => current.map(item => ({...item, messages: clear(item.messages)}))); }} onRegenerate={!loading && message.role === "assistant" && index === messages.length-1 ? () => { const question=messages.slice(0,index).reverse().find(item=>item.role==="user"); if(question) void submit(question.content, question.documents, true); } : undefined} /></div>)}</div>
          {awayFromLatest && <button className="jump-latest" aria-label="Jump to latest message" onClick={() => window.scrollTo({ top: document.documentElement.scrollHeight, behavior: animate ? "smooth" : "auto" })}><ArrowDown size={17}/></button>}
          <div className="conversation-composer"><ChatInput key={`${sessionId}:${draftVersion}`} onSend={submit} onStop={stopResearch} loading={loading} mode={responseMode} onModeChange={setResponseMode} /></div>
        </>}
      </section>}
    </div>
    <CitizenGuideDialog open={citizenGuideSlide !== null} initialSlide={citizenGuideSlide ?? 0} onClose={() => setCitizenGuideSlide(null)} onStart={(prompt) => { setCitizenGuideSlide(null); void submit(prompt); }}/>
    {settingsOpen && <div className="modal-backdrop" onMouseDown={() => setSettingsOpen(false)}><div ref={settingsRef} role="dialog" aria-modal="true" aria-label="Settings" className="settings-dialog" onMouseDown={event => event.stopPropagation()}>
      <div className="dialog-heading settings-heading"><div><h2>Settings</h2><p>Make the workspace feel right for you.</p></div><button aria-label="Close settings" className="icon-button" onClick={() => setSettingsOpen(false)}><X size={18} /></button></div>
      <div className="settings-account"><div><strong>{user.name}</strong><span>{user.email}</span></div><b>{role}</b></div>
      <section className="settings-section"><h3>Experience</h3>
        <div className="setting-block"><div className="setting-copy"><strong>Appearance</strong><small>A calm palette for daytime or low light.</small></div><div className="theme-choice" role="group" aria-label="Appearance"><button aria-pressed={theme === "paper"} onClick={() => setTheme("paper")}><i className="paper-swatch"/>Light</button><button aria-pressed={theme === "ink"} onClick={() => setTheme("ink")}><i className="ink-swatch"/>Dark</button></div></div>
        <div className="setting-block setting-stack"><div className="setting-copy"><strong>Default research depth</strong><small>You can still change this beside any question.</small></div><div className="mode-choice" role="group" aria-label="Default response mode">{(["auto","fast","deep"] as RequestedResponseMode[]).map(mode => <button key={mode} aria-pressed={responseMode === mode} onClick={() => setResponseMode(mode)}>{mode === "auto" ? "Auto" : mode === "fast" ? "Fast" : "Deep review"}</button>)}</div></div>
        <label className="setting-block"><span className="setting-copy"><strong>Ambient motion</strong><small>Includes the scales and subtle background glow.</small></span><span className="premium-switch"><input type="checkbox" checked={animate} onChange={event => setAnimate(event.target.checked)} /><i/></span></label>
      </section>
      <section className="settings-section"><h3>History & privacy</h3>
        <label className="setting-block"><span className="setting-copy"><strong>Remember chats in this tab</strong><small>Keep up to 20 conversations. Nothing is synced across devices.</small></span><span className="premium-switch"><input type="checkbox" checked={rememberHistory} onChange={event => setRememberHistory(event.target.checked)} /><i/></span></label>
        <details className="settings-privacy"><summary>Documents, voice & retention<span>View details</span></summary><UploadPrivacy/><p>Voice uses your browser’s recognition service. English is currently validated; transcripts remain editable and never send automatically.</p></details>
      </section>
      <section className="settings-section"><h3>Corpus connection</h3><div className="corpus-status"><span className={progress?.validation_status === "pass" ? "is-online" : ""}/><div><strong>{progress?.validation_status === "pass" ? "Verified corpus ready" : "Corpus status unavailable"}</strong><small>{progress ? `${progress.canonical_documents.toLocaleString()} sources · ${(progress.global_points ?? progress.qdrant_points).toLocaleString()} searchable passages` : "Reconnect to check source availability."}</small></div></div></section>
      <div className="settings-actions"><button disabled={loading} onClick={() => { setHistory([]); setMessages([]); setSessionId(null); setActiveChatId(crypto.randomUUID()); setDraftVersion(value => value + 1); }}>Clear this tab’s history</button><button disabled={loading} onClick={() => { setSettingsOpen(false); void signOut(); }}><LogOut size={15} />Sign out</button></div>
      <details className="desktop-details"><summary>Desktop app status</summary><DesktopReadiness /></details>
    </div></div>}
    {guideOpen && <div className="modal-backdrop" onMouseDown={() => setGuideOpen(false)}><div ref={guideRef} role="dialog" aria-modal="true" aria-label="Getting started" className="guide-dialog" onMouseDown={event=>event.stopPropagation()}>
      <div className="dialog-heading"><div><p className="text-xs text-neutral-400">A quick introduction</p><h2>From question to clarity.</h2></div><button className="icon-button" aria-label="Close guide" onClick={() => setGuideOpen(false)}><X size={18} /></button></div>
      <div className="visual-guide">
        <section><div className="guide-picture"><MessageSquare size={44} strokeWidth={1.3} /><span className="guide-line long" /><span className="guide-line" /></div><span className="step-number">01</span><h3>{role==="citizen" ? "Tell us what happened" : "Start with the facts"}</h3><p>Ask a question in chat. Include the details that matter, without unnecessary personal information.</p></section>
        <section><div className="guide-picture"><Scale size={48} strokeWidth={1.3} /><span className="guide-dots"><i/><i/><i/></span></div><span className="step-number">02</span><h3>Choose your depth</h3><p>Auto picks a workflow. Fast finds source passages; Deep Review works through a fuller analysis.</p></section>
        <section><div className="guide-picture"><BookOpenText size={46} strokeWidth={1.3} /><ShieldCheck className="guide-check" size={23} /></div><span className="step-number">03</span><h3>{role==="citizen" ? "Check the source" : "Build on the evidence"}</h3><p>{role==="citizen" ? "Expand a citation to read the passage. Copy useful references and return to past chats in the sidebar." : "Open your matter workspace to add evidence, review documents and prepare a draft or strategy."}</p></section>
      </div><button className="button-primary mt-8" onClick={()=>setGuideOpen(false)}>Got it, let’s begin</button><p className="mt-4 text-xs text-neutral-400">Research support, not a substitute for professional judgement.</p>
    </div></div>}
  </main>;
}
