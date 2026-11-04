"use client";

import { ArrowDown, BookOpenText, ChevronRight, Search, BriefcaseBusiness, Check, FilePenLine, Fingerprint, HelpCircle, History, LogOut, Menu, MessageSquare, MoreHorizontal, Pencil, Pin, PinOff, Plus, Scale, ScanSearch, Settings, ShieldCheck, Trash2, Undo2, X, Zap } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import AuthModal from "@/components/AuthModal";
import BrandLogo from "@/components/BrandLogo";
import ChatInput from "@/components/ChatInput";
import { scopeLockedReason } from "@/lib/police-presentation";
import MessageBubble from "@/components/MessageBubble";
import CitizenGuideDialog from "@/components/CitizenGuideDialog";
import UploadPrivacy from "@/components/UploadPrivacy";
import { legalCategory } from "@/lib/answer-presentation";
import ProfessionalWorkspace from "@/components/ProfessionalWorkspace";
import { useDialogFocus } from "@/components/useDialogFocus";
import AdminWorkspace from "@/components/AdminWorkspace";
import AccountDialog from "@/components/platform/AccountDialog";
import AccountGate from "@/components/platform/AccountGate";
import HistoryPanel from "@/components/platform/HistoryPanel";
import { listHistorySessions, setSessionPinned } from "@/lib/api-platform";
import { mergeById } from "@/lib/history-view";
import { DEFAULT_LIMITS, followJob, forgetActiveJob, readActiveJob, rememberActiveJob } from "@/lib/job-stream";
import { bandwidthPlan, readPreferences, PREFERENCES_EVENT } from "@/lib/preferences";
import type { HistorySession } from "@/lib/types-platform";
import { HelplineNotice } from "@/components/HelplineNotice";
import CitizenWorkspace, { CITIZEN_TOOLS, type CitizenTool } from "@/components/citizen/CitizenWorkspace";
import DueSoonStrip from "@/components/citizen/DueSoonStrip";
import { LangSwitcher } from "@/components/citizen/shared";
import { useCitizenLang } from "@/components/citizen/useCitizenLang";
import { readDraft, restoreStoredMessages, syncHistoryRow } from "@/lib/citizen-chat";
import type { UiKey } from "@/lib/citizen-i18n";
import { onSessionExpired } from "@/lib/session-expiry";
import { ApiError, apiUrl, cancelDeepReviewJob, chatWithCorpus, checkForHelplines, deleteChatSession, getChatSession, renameChatSession, getDeepReviewJob, getIngestionProgress, getMe, logout, refreshSession, listCases } from "@/lib/api";
import type { ChatMessage, CitizenDocument, IngestionProgress, RequestedResponseMode, User, LegalCase } from "@/lib/types";

const ROLE_EXPERIENCES = {
  citizen: {
    nav: "Legal help & research",
    workspace: "My legal research",
    eyebrow: "Citizen legal information",
    heading: "What legal issue can we help you understand?",
    description: "Receive plain-language legal information, practical procedural steps and page-linked authorities. The assistant abstains when the verified corpus is insufficient.",
    placeholder: "Describe your legal question in your own words…",
    badge: "Citizen assistant",
    // Every chip is measured against the live corpus: each answers directly in
    // Fast mode with cited authority. "Contract basics" was removed because the
    // Indian Contract Act is not in the corpus at all, so it could only ever
    // abstain - correct behaviour, but a poor thing to advertise on the
    // landing screen.
    suggestions: [
      { title: "Filing an FIR", text: "What is the procedure for filing an FIR?" },
      { title: "Stolen phone", text: "My phone was stolen, what do I do?" },
      { title: "Police stop", text: "What are my rights if the police stop me?" },
      { title: "Fundamental rights", text: "Explain the right to equality under Article 14 in plain language." },
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

/** How this page follows a Deep review. The logic and its tests are in lib/job-stream. */
function jobFollower() {
  return {
    ...DEFAULT_LIMITS,
    pollIntervalMs: bandwidthPlan(readPreferences().lowBandwidth).pollIntervalMs,
    openStream: (jobId: string, lastEventId: number, signal?: AbortSignal) => fetch(`${apiUrl()}/jobs/${encodeURIComponent(jobId)}/events`, {
      credentials: "include",
      signal,
      headers: { Accept: "text/event-stream", ...(lastEventId ? { "Last-Event-ID": String(lastEventId) } : {}) },
    }),
    getJob: getDeepReviewJob,
    sleep: (ms: number, signal?: AbortSignal) => new Promise<void>((resolve) => {
      const timer = window.setTimeout(resolve, ms);
      signal?.addEventListener("abort", () => { window.clearTimeout(timer); resolve(); }, { once: true });
    }),
  };
}

function savedChatFrom(item: HistorySession): SavedChat {
  return {
    id: item.id,
    title: item.title,
    // Bodies load on demand; a sidebar must not fetch every message of every
    // conversation, which for a case session includes evidence.
    messages: [],
    sessionId: item.id,
    updatedAt: Date.parse(item.updated_at),
    preview: item.last_message_preview ?? undefined,
    messageCount: item.message_count,
    caseId: item.case_id,
    pinned: item.pinned,
    matter: item.matter,
  };
}

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
  /** The matter this conversation may also read. Null is public law only. */
  caseId?: string | null;
  /** A name the person gave to group conversations. Unrelated to a case. */
  matter?: string | null;
};

export default function HomePage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState<IngestionProgress | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  // Which matter, if any, a professional's question may also read. Null is
  // the safe default and the only value a citizen ever has: public law only.
  const [chatCaseId, setChatCaseId] = useState<string | null>(null);
  const [chatCases, setChatCases] = useState<LegalCase[]>([]);
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
  const [historyNotice, setHistoryNotice] = useState("");
  const [historyCursor, setHistoryCursor] = useState<string | null>(null);
  const [historyVersion, setHistoryVersion] = useState(0);
  const [historyPanelOpen, setHistoryPanelOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [erasedReceipt, setErasedReceipt] = useState<string | null>(null);
  const [sessionExpired, setSessionExpired] = useState(false);
  const [restoredDraft, setRestoredDraft] = useState("");
  const [citizenTool, setCitizenTool] = useState<{ tool: CitizenTool | null; nonce: number } | null>(null);
  // Which conversation the screen is showing. A slow load for another one must not overwrite it.
  const openingChat = useRef<string | null>(null);
  const expiredUserId = useRef<string | null>(null);
  const { t: citizenText } = useCitizenLang(user?.role === "citizen");
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
    // Restoring the session must never be able to hang the app. A fetch that
    // never settles -- the API restarting, the network dropping mid-flight --
    // left `finally` unreached, so authChecked stayed false and the whole
    // workspace sat on its loading icon with no way out and nothing on screen.
    // Whatever happens, after this many milliseconds we decide: signed in if
    // the call came back, signed out if it did not.
    const AUTH_RESTORE_TIMEOUT_MS = 6000;
    const withTimeout = <T,>(work: Promise<T>): Promise<T> =>
      Promise.race([
        work,
        new Promise<T>((_, reject) =>
          setTimeout(() => reject(new Error("auth restore timed out")), AUTH_RESTORE_TIMEOUT_MS)),
      ]);
    const restoreAuth = async () => {
      try { const current = await withTimeout(getMe()); if (mounted) setUser(current); }
      catch { try { const current = await withTimeout(refreshSession()); if (mounted) setUser(current); } catch { if (mounted) setUser(null); } }
      finally { if (mounted) setAuthChecked(true); }
    };
    const poll = async () => { try { const next = await getIngestionProgress(); if (mounted) setProgress(next); } catch { if (mounted) setProgress(null); } };
    // Low-bandwidth mode drops this background check. Re-read on each tick, so the
    // setting takes effect without a reload.
    const pollIfWanted = () => { if (bandwidthPlan(readPreferences().lowBandwidth).pollCorpusStatus) void poll(); };
    restoreAuth(); pollIfWanted(); const interval = setInterval(pollIfWanted, 30_000);
    window.addEventListener(PREFERENCES_EVENT, pollIfWanted);
    return () => { mounted = false; clearInterval(interval); window.removeEventListener(PREFERENCES_EVENT, pollIfWanted); };
  }, []);

  // A refresh the server refused means this session is over. Show sign-in and
  // keep the conversation and the draft, rather than leaving a signed-in screen
  // where every feature fails.
  useEffect(() => onSessionExpired(() => {
    setUser(current => {
      if (!current) return current;
      setRestoredDraft(readDraft(window.sessionStorage));
      expiredUserId.current = current.id;
      setSessionExpired(true);
      return null;
    });
  }), []);

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
        const pageSize = bandwidthPlan(readPreferences().lowBandwidth).historyPageSize;
        // Pins separately: one pinned long ago must not wait for a person to page
        // back to it before it reappears.
        const [stored, pinned] = await Promise.all([listHistorySessions({ limit: pageSize }), listHistorySessions({ limit: 5, pinned: true })]);
        if (cancelled) return;
        setHistory(mergeById(pinned.items.map(savedChatFrom), stored.items.map(savedChatFrom)));
        setHistoryCursor(stored.next_cursor);
      } catch {
        // An offline or unauthenticated read must not blank the console.
        if (!cancelled) { setHistory([]); setHistoryCursor(null); }
      } finally {
        if (!cancelled) setHistoryReady(true);
      }
    })();
    return () => { cancelled = true; };
  }, [user, historyVersion]);

  useEffect(() => {
    if (!user || !historyReady || loading || !activeChatId || !messages.length) return;
    // Keep the sidebar in step with the live conversation. The server already
    // holds the durable copy; this only avoids a round-trip after each answer.
    setHistory(current => syncHistoryRow(current, { activeChatId, sessionId, messages, caseId: chatCaseId }, Date.now()));
  }, [messages, sessionId, loading, user, historyReady, activeChatId, chatCaseId]);

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
    if (user) forgetActiveJob(window.sessionStorage, user.id);
    setLoading(false);
    setMessages(current => current.map(message => message.id === active.assistantId ? { ...message, loading: false, stopped: true, content: "Response stopped." } : message));
    if (user) { try { forgetActiveJob(window.sessionStorage, user.id); } catch { /* Storage disabled. */ } }
    if (active.jobId) void cancelDeepReviewJob(active.jobId).catch(() => {
      setMessages(current => current.map(message => message.id === active.assistantId ? { ...message, content: "Stopped here. The server could not confirm cancellation and may finish the queued review." } : message));
    });
  };

  const submit = async (query: string, documents: CitizenDocument[] = [], regenerate = false, editIndex?: number) => {
    if (!query.trim() || loading || !user) return;
    setRestoredDraft("");
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
    // Not awaited: the notice should appear at once, while the answer is still being written.
    if (user.role === "citizen") void checkForHelplines(query.trim()).then(contacts => {
      if (contacts.length) setMessages(current => current.map(message => message.id === assistantId ? { ...message, helplines: contacts } : message));
    });
    try {
      const response = await chatWithCorpus(query.trim(), targetSession, availableDocuments.length ? "deep" : responseMode, availableDocuments, operation.controller.signal, priorMessages, chatCaseId);
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
        try { rememberActiveJob(window.sessionStorage, user.id, { jobId: response.job_id, sessionId: response.session_id, startedAt: Date.now() }); } catch { /* Storage disabled. */ }
        const job = await followJob(response.job_id, jobFollower(), {
          signal: operation.controller.signal,
          onUpdate: (view) => setMessages((current) => current.map((message) => message.id === assistantId ? {
            ...message,
            loading: true,
            stageLabel: view.stageLabel ?? (view.queuePosition ? `Waiting in line, position ${view.queuePosition}` : null),
            jobProgress: view.progress,
          } : message)),
        });
        try { forgetActiveJob(window.sessionStorage, user.id); } catch { /* Storage disabled. */ }
        if (operation.controller.signal.aborted) return;
        if (job.status === "succeeded" && job.result) {
          const result = job.result;
          setMessages((current) => current.map((message) => message.id === assistantId ? {
            ...message,
            messageId: result.message_id,
            content: result.answer,
            loading: false,
            citations: result.citations,
            confidenceScore: result.confidence_score,
            evidenceStrength: result.evidence_strength,
            sectionConfidence: result.section_confidence,
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
          return;
        }
        throw new ApiError(job.error_message || `Deep Review ${job.status}.`, 500);
      }
      setMessages((current) => current.map((message) => message.id === assistantId ? { ...message, messageId: response.message_id ?? undefined, content: response.answer, loading: false, citations: response.citations, confidenceScore: response.confidence_score, evidenceStrength: response.evidence_strength, sectionConfidence: response.section_confidence, responseMode: response.response_mode, requestedMode: response.requested_mode, routingReason: response.routing_reason, routingSignals: response.routing_signals, timingsMs: response.timings_ms, pipelineMetrics: response.pipeline_metrics, latencyTargetMs: response.latency_target_ms, targetMet: response.target_met, clientElapsedMs: Math.round(performance.now() - requestStarted) } : message));
    } catch (error) {
      if (operation.controller.signal.aborted) return;
      forgetActiveJob(window.sessionStorage, user.id);
      const detail = error instanceof ApiError ? error.message : "The legal corpus is unavailable. Confirm the backend is healthy and try again.";
      setMessages((current) => current.map((item) => item.id === assistantId ? { ...item, content: "", loading: false, error: detail } : item));
    } finally { if (activeRequest.current === operation) { activeRequest.current = null; setLoading(false); } }
  };

  const signOut = async () => { await logout().catch(() => undefined); setUser(null); setMessages([]); setSessionId(null); setActiveChatId(null); setView("research"); setResponseMode("auto"); setMobileNav(false); };
  const hasProfessionalWorkspace = user?.role === "police" || user?.role === "advocate";
  useEffect(() => {
    if (!hasProfessionalWorkspace) { setChatCases([]); setChatCaseId(null); return; }
    listCases().then((response) => setChatCases(response.cases)).catch(() => setChatCases([]));
  }, [hasProfessionalWorkspace]);
  const hasOperationsWorkspace = hasProfessionalWorkspace || user?.role === "admin";
  const resetResearch = (caseId: string | null = null) => { openingChat.current = null; setRestoredDraft(""); setMessages([]); setSessionId(null); setActiveChatId(crypto.randomUUID()); setChatCaseId(caseId); setDraftVersion(value => value + 1); setView("research"); setMobileNav(false); window.scrollTo({ top: 0, behavior: "auto" }); };
  const openSavedChat = (item: SavedChat) => {
    setChatMenuId(null);
    setActiveChatId(item.id);
    // Restoring the conversation without its scope would let the next
    // question in an open matter thread silently run on public law alone.
    setChatCaseId(item.caseId ?? null);
    setSessionId(item.sessionId);
    setDraftVersion(value => value + 1);
    setView("research");
    setMobileNav(false);
    window.scrollTo({ top: 0, behavior: "auto" });

    openingChat.current = item.id;
    if (item.messages.length || !item.sessionId) { setMessages(item.messages); return; }
    // Sidebar rows carry no bodies. Load this conversation's messages from the
    // server, with their stored citations and confidence scores intact.
    setMessages([{ id: crypto.randomUUID(), role: "assistant", content: "", timestamp: Date.now(), loading: true, requestedMode: "fast" }]);
    void (async () => {
      try {
        const stored = await getChatSession(item.sessionId!);
        // The person may have opened another chat while this one loaded.
        if (openingChat.current !== item.id) return;
        const restored = restoreStoredMessages(stored.messages);
        setMessages(restored);
        setHistory(current => current.map(row => row.id === item.id ? { ...row, messages: restored, messageCount: Math.max(row.messageCount ?? 0, restored.length) } : row));
      } catch {
        if (openingChat.current !== item.id) return;
        setMessages([{ id: crypto.randomUUID(), role: "assistant", content: "", timestamp: Date.now(), error: "This conversation could not be loaded. Check your connection and try again." }]);
      }
    })();
  };
  const togglePinned = async (item: SavedChat) => {
    setChatMenuId(null);
    if (!item.sessionId) return;
    // Saved on the server, so it is there on the next device and after a reload.
    try {
      await setSessionPinned(item.sessionId, !item.pinned);
      setHistory(current => current.map(chat => chat.id === item.id ? { ...chat, pinned: !chat.pinned } : chat));
      setHistoryNotice(item.pinned ? "Chat moved back to recent." : "Chat pinned for quick access.");
    } catch (error) {
      setHistoryNotice(error instanceof ApiError ? error.message : "That could not be saved.");
    }
  };
  const loadOlderChats = async () => {
    if (!historyCursor) return;
    try {
      const page = await listHistorySessions({ limit: bandwidthPlan(readPreferences().lowBandwidth).historyPageSize, cursor: historyCursor });
      setHistory(current => mergeById(current, page.items.map(savedChatFrom)));
      setHistoryCursor(page.next_cursor);
    } catch {
      setHistoryNotice("Older conversations could not be loaded.");
    }
  };
  const openFromPanel = (item: HistorySession) => {
    setHistoryPanelOpen(false);
    openSavedChat(history.find(chat => chat.id === item.id) ?? savedChatFrom(item));
  };
  const saveChatTitle = (item: SavedChat) => {
    const title = renameDraft.trim().slice(0, 90);
    if (title) {
      setHistory(current => current.map(chat => chat.id === item.id ? { ...chat, title, customTitle: true } : chat));
      if (item.sessionId) void renameChatSession(item.sessionId, title).catch(() => setHistoryNotice("The new name could not be saved."));
    }
    setRenamingChatId(null);
    setChatMenuId(null);
  };
  const deleteChat = async (item: SavedChat) => {
    setChatMenuId(null);
    if (!window.confirm("Delete this conversation permanently? This cannot be undone.")) return;
    try {
      if (item.sessionId) await deleteChatSession(item.sessionId);
      setHistory(current => current.filter(chat => chat.id !== item.id));
      setHistoryNotice("Chat deleted.");
      if (activeChatId === item.id) resetResearch();
    } catch {
      setHistoryNotice("The chat could not be deleted. Please try again.");
    }
  };
  // The nonce matters: clicking the same sidebar link twice must reopen
  // that view, and a bare value would not change on the second click.
  const [workspaceView, setWorkspaceView] = useState<{ view: string; nonce: number } | null>(null);
  const [workspaceVisited, setWorkspaceVisited] = useState(false);
  useEffect(() => { if (view === "workspace") setWorkspaceVisited(true); }, [view]);
  useEffect(() => { setWorkspaceVisited(false); }, [user?.id]);
  const openTool = (target?: string) => {
    setView("workspace"); setMobileNav(false);
    setWorkspaceView(current => ({ view: target || "casefile", nonce: (current?.nonce ?? 0) + 1 }));
  };
  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => { if (event.key === "Escape") { setMobileNav(false); setSettingsOpen(false); setGuideOpen(false); setChatMenuId(null); setRenamingChatId(null); } };
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, []);

  // A Deep review keeps running on the server through a reload. Pick it back up,
  // rather than leaving the person to think it was lost and pay for another.
  const resumedFor = useRef<string | null>(null);
  useEffect(() => {
    if (!user || !historyReady || resumedFor.current === user.id) return;
    resumedFor.current = user.id;
    let stored: ReturnType<typeof readActiveJob> = null;
    try { stored = readActiveJob(window.sessionStorage, user.id); } catch { /* Storage disabled. */ }
    if (!stored || activeRequest.current) return;
    const resume = stored;
    const assistantId = crypto.randomUUID();
    const operation = { controller: new AbortController(), assistantId, jobId: resume.jobId };
    activeRequest.current = operation;
    setLoading(true);
    setSessionId(resume.sessionId);
    setActiveChatId(resume.sessionId);
    void (async () => {
      try {
        const conversation = await getChatSession(resume.sessionId);
        setChatCaseId(conversation.case_id ?? null);
        const shown: ChatMessage[] = conversation.messages.map(message => ({ id: message.id, messageId: message.id, role: message.role === "user" ? "user" : "assistant", content: message.content, citations: message.citations, confidenceScore: message.confidence_score ?? undefined, evidenceStrength: message.confidence_score === 0 ? "insufficient" : undefined, timestamp: Date.parse(message.created_at) }));
        setMessages([...shown, { id: assistantId, role: "assistant", content: "", timestamp: resume.startedAt, loading: true, requestedMode: "deep", responseMode: "deep", stageLabel: null, jobProgress: 0 }]);
        const job = await followJob(resume.jobId, jobFollower(), {
          signal: operation.controller.signal,
          onUpdate: (view) => setMessages(current => current.map(message => message.id === assistantId ? { ...message, loading: true, stageLabel: view.stageLabel ?? (view.queuePosition ? `Waiting in line, position ${view.queuePosition}` : null), jobProgress: view.progress } : message)),
        });
        if (operation.controller.signal.aborted) return;
        if (job.status === "succeeded" && job.result) {
          const result = job.result;
          setMessages(current => current.map(message => message.id === assistantId ? { ...message, messageId: result.message_id, content: result.answer, loading: false, citations: result.citations, confidenceScore: result.confidence_score, evidenceStrength: result.evidence_strength, responseMode: "deep", timingsMs: result.timings_ms, pipelineMetrics: result.pipeline_metrics, stageLabel: null, jobProgress: null } : message));
        } else {
          setMessages(current => current.map(message => message.id === assistantId ? { ...message, content: "", loading: false, error: job.error_message || `Deep review ${job.status}.` } : message));
        }
      } catch (error) {
        if (operation.controller.signal.aborted) return;
        setMessages(current => current.map(message => message.id === assistantId ? { ...message, content: "", loading: false, error: error instanceof ApiError ? error.message : "Progress on this review could not be followed. It may still finish: reopen this chat shortly." } : message));
      } finally {
        try { forgetActiveJob(window.sessionStorage, user.id); } catch { /* Storage disabled. */ }
        if (activeRequest.current === operation) { activeRequest.current = null; setLoading(false); }
      }
    })();
  }, [user, historyReady]);

  if (!authChecked) return <main className="grid min-h-screen place-items-center"><Scale size={24} className="text-neutral-400" aria-label="Loading workspace" /></main>;
  if (erasedReceipt) return <main className="erased-screen"><div><h1>Your account has been erased.</h1><p>Your account, conversations, case records and files have been removed from this installation. Backups, if the operator keeps any, leave as they age out.</p><p>Your receipt, should you need to quote it. It does not identify you:</p><code>{erasedReceipt}</code></div></main>;
  if (!user) return <>
    {sessionExpired && <p className="ctz-session-expired" role="status">{citizenText("sessionExpired")}</p>}
    <AuthModal onSuccess={(next) => {
      setSessionExpired(false);
      // The conversation on screen stays only if the same person came back.
      if (expiredUserId.current && expiredUserId.current !== next.id) { setMessages([]); setSessionId(null); setActiveChatId(null); setRestoredDraft(""); }
      setUser(next);
    }} progress={progress} />
  </>;

  const role = user.role;
  const openCitizenTool = (tool: CitizenTool | null) => { setCitizenTool(current => ({ tool, nonce: (current?.nonce ?? 0) + 1 })); setView("workspace"); setMobileNav(false); };
  const tools: { title: string; icon: typeof Scale; target?: string; citizenTool?: CitizenTool }[] = role === "citizen" ? CITIZEN_TOOLS.map(tool => ({ title: citizenText(tool.title as UiKey), icon: tool.icon, citizenTool: tool.id })) : role === "police" ? [
    { title: "Investigations", icon: Fingerprint, target: "" },
    { title: "FIR drafting", icon: FilePenLine, target: "agent" },
    { title: "Evidence & documents", icon: ScanSearch, target: "documents" },
  ] : role === "advocate" ? [
    { title: "Your cases", icon: BriefcaseBusiness, target: "" },
    { title: "Build a strategy", icon: Scale, target: "agent" },
    { title: "Review documents", icon: ScanSearch, target: "documents" },
  ] : [{ title: "Manage workspace", icon: Settings, target: "" }];
  const pinnedChats = history.filter(item => item.pinned).sort((a, b) => (b.updatedAt ?? 0) - (a.updatedAt ?? 0));
  const recentChats = history.filter(item => !item.pinned).sort((a, b) => (b.updatedAt ?? 0) - (a.updatedAt ?? 0));
  const caseTitle = (caseId: string | null | undefined) => chatCases.find(item => item.id === caseId)?.title ?? "Matter";
  // A citizen has no matters, so their list is never split.
  const publicChats = hasProfessionalWorkspace ? recentChats.filter(item => !item.caseId) : recentChats;
  const matterChats = hasProfessionalWorkspace ? recentChats.filter(item => item.caseId) : [];
  const chatRow = (item: SavedChat) => <div className={`chat-history-row ${item.id === activeChatId ? "selected" : ""}`} key={item.id}>
    {renamingChatId === item.id ? <form className="chat-rename" onSubmit={event => { event.preventDefault(); saveChatTitle(item); }}><input autoFocus aria-label="Rename chat" value={renameDraft} maxLength={90} onChange={event => setRenameDraft(event.target.value)} onKeyDown={event => { if (event.key === "Escape") setRenamingChatId(null); }}/><button aria-label="Save chat name" disabled={!renameDraft.trim()}><Check size={13}/></button></form> : <button disabled={loading} className="chat-open" aria-current={item.id === activeChatId ? "page" : undefined} title={item.title} onClick={() => openSavedChat(item)}>{item.pinned ? <Pin size={13}/> : <MessageSquare size={14}/>}<span>{item.title}</span></button>}
    {item.matter && <span className="chat-scope-tag" title={`Matter: ${item.matter}`}>{item.matter}</span>}
    {item.caseId && <span className="chat-scope-tag" title={`Reads the law and the files in ${caseTitle(item.caseId)}`}>{caseTitle(item.caseId)}</span>}
    {renamingChatId !== item.id && <button className="chat-menu-trigger" aria-label={`Chat options for ${item.title}`} aria-expanded={chatMenuId === item.id} onClick={() => setChatMenuId(current => current === item.id ? null : item.id)}><MoreHorizontal size={15}/></button>}
    {chatMenuId === item.id && <div className="chat-menu" role="menu"><button role="menuitem" onClick={() => void togglePinned(item)}>{item.pinned ? <PinOff size={14}/> : <Pin size={14}/>} {item.pinned ? "Unpin" : "Pin chat"}</button><button role="menuitem" onClick={() => { setRenamingChatId(item.id); setRenameDraft(item.title); setChatMenuId(null); }}><Pencil size={14}/>Rename</button><button role="menuitem" className="is-danger" onClick={() => deleteChat(item)}><Trash2 size={14}/>Delete</button></div>}
  </div>;

  return <main data-role={role} data-motion={animate ? "on" : "off"} className="app-shell">
    <aside aria-label="Main navigation" aria-hidden={compactNavigation && !mobileNav} ref={node => { if(node) node.inert = compactNavigation && !mobileNav; }} className={`app-sidebar ${mobileNav ? "is-open" : ""}`}>
      <div className="sidebar-brand"><BrandLogo /><button className="icon-button lg:hidden" onClick={() => setMobileNav(false)} aria-label="Close navigation"><X size={18} /></button></div>
      <button disabled={loading} className="new-chat-button" onClick={() => { resetResearch(); setMobileNav(false); }}><Plus size={18} />{citizenText("newChat")}</button>
      <button className="sidebar-search" onClick={() => { setMobileNav(false); setHistoryPanelOpen(true); }}><Search size={15} aria-hidden="true" />Search chats</button>
      <nav className="feature-nav" aria-label="Features">{tools.map(tool => <button key={tool.title} onClick={() => { if (tool.citizenTool) openCitizenTool(tool.citizenTool); else openTool(tool.target); }}><tool.icon size={18} strokeWidth={1.65} /><span>{tool.title}</span></button>)}</nav>
      <div className="chat-history">{pinnedChats.length > 0 && <><div className="history-heading"><span>Pinned <b>{pinnedChats.length}/5</b></span><Pin size={13}/></div>{pinnedChats.map(chatRow)}</>}<div className="history-heading"><span>{hasProfessionalWorkspace ? "Law-only chats" : citizenText("recentChats")}</span><History size={14}/></div>{publicChats.length ? publicChats.map(chatRow) : !pinnedChats.length && !matterChats.length && <p>Your conversations will appear here.</p>}{hasProfessionalWorkspace && <><div className="history-heading"><span>Case chats</span><BriefcaseBusiness size={13}/></div>{matterChats.length ? matterChats.map(chatRow) : <p>Open a case and ask a question there to start one.</p>}</>}{historyCursor && <button type="button" className="ctz-load-more" onClick={() => void loadOlderChats()}>{citizenText("loadMore")}</button>}</div>
      <div className="sidebar-bottom"><button onClick={() => { setMobileNav(false); role === "citizen" ? setCitizenGuideSlide(0) : setGuideOpen(true); }}><HelpCircle size={17} />{citizenText("gettingStarted")}</button><button onClick={() => { setMobileNav(false); setSettingsOpen(true); }}><Settings size={17} />{citizenText("settings")}<span className="ml-auto text-[11px] capitalize text-neutral-400">{role}</span></button></div>
    </aside>
    {mobileNav && <button aria-label="Dismiss navigation" className="sidebar-scrim" onClick={() => setMobileNav(false)} />}
    {historyNotice && <div className="history-toast" role="status"><span>{historyNotice}</span><button aria-label="Dismiss notification" onClick={() => setHistoryNotice("")}><X size={13}/></button></div>}
    <div className="app-content" id="main-content" ref={node => { if(node) node.inert = compactNavigation && mobileNav; }}>
      <header className="workspace-header"><button className="icon-button lg:hidden" aria-label="Open navigation" onClick={() => setMobileNav(true)}><Menu size={20} /></button><span>{view === "workspace" ? role === "citizen" ? " " : role === "police" ? "Investigation workspace" : role === "advocate" ? "Your case workspace" : "Administration" : " "}</span>{role === "citizen" && view !== "workspace" && <LangSwitcher/>}{view === "workspace" && <button className="text-sm text-neutral-500" onClick={() => setView("research")}><MessageSquare size={16} className="mr-2 inline" />{citizenText("backToChat")}</button>}</header>
      {view === "workspace" && role === "citizen" && <CitizenWorkspace requested={citizenTool} onAsk={(question) => { resetResearch(); void submit(question); }} />}
      {/* Stays mounted once opened: going back to chat must not lose an unsaved
          narrative or the selected case. */}
      {hasProfessionalWorkspace && workspaceVisited && <div hidden={view !== "workspace"}><ProfessionalWorkspace
          key={user.id}
          user={user}
          chats={history.filter(item => item.caseId).map(item => ({ id: item.id, sessionId: item.sessionId, title: item.title, caseId: item.caseId ?? null, updatedAt: item.updatedAt ?? 0 }))}
          onCasesChange={setChatCases}
          onNewMatterChat={(caseId) => resetResearch(caseId)}
          onOpenMatterChat={(chatId) => { const saved = history.find(item => item.id === chatId); if (saved) openSavedChat(saved); }}
          requestedView={workspaceView}
        /></div>}
      {view === "workspace" && hasOperationsWorkspace ? role === "admin" ? <AdminWorkspace /> : null : view === "workspace" ? null :
      <section className={`chat-workspace ${messages.length ? "has-conversation" : ""}`}>
        {!messages.length ? <div className="chat-welcome">
          {role === "citizen" && <DueSoonStrip onOpen={() => openCitizenTool("matter")}/>}
          <div className="welcome-symbol"><Scale size={32} strokeWidth={1.3} /></div>
          <h1>{role === "citizen" ? citizenText("welcomeHeading") : role === "police" ? "What are you investigating?" : role === "advocate" ? "Where does your argument begin?" : "What would you like to research?"}</h1>
          <p>{role === "citizen" ? citizenText("welcomeLead") : role === "police" ? "Explore procedure, preserve evidence, and build your record." : role === "advocate" ? "Find authority. Explore both sides. Refine your position." : "Explore your legal corpus."}</p>
          <ChatInput key={`${sessionId}:${draftVersion}`} onSend={submit} onStop={stopResearch} loading={loading} mode={responseMode} onModeChange={setResponseMode} cases={chatCases} caseId={chatCaseId} onCaseChange={setChatCaseId} scopeLockedReason={scopeLockedReason(sessionId)} placeholder={experience.placeholder} redactBeforeAttach={role === "citizen"} initialDraft={restoredDraft} />
          {role === "citizen" && <div className="ctz-welcome-tools"><span>{citizenText("openTools")}</span>{CITIZEN_TOOLS.slice(0, 4).map(tool => <button type="button" key={tool.id} onClick={() => openCitizenTool(tool.id)}><tool.icon size={15} strokeWidth={1.6} aria-hidden="true"/>{citizenText(tool.title as UiKey)}</button>)}</div>}
          <div className="prompt-shortcuts">{experience.suggestions.map((suggestion,index) => { const Icon = [FilePenLine, ScanSearch, ShieldCheck, BookOpenText][index]; return <button key={suggestion.title} disabled={loading} onClick={() => void submit(suggestion.text)}><Icon size={16} strokeWidth={1.6} />{suggestion.title}</button>; })}</div>
          <button className="guide-invite" onClick={() => role === "citizen" ? setCitizenGuideSlide(0) : setGuideOpen(true)}><HelpCircle size={14} />First time here? Take a quick look</button>
        </div> : <>
          <div className="conversation">{messages.map((message,index) => <div key={message.id} ref={index === messages.length-1 ? latestMessage : undefined}>{!!message.helplines?.length && <HelplineNotice contacts={message.helplines}/>}<MessageBubble message={message} citizen={role === "citizen"} onLegalAid={role === "citizen" ? () => openCitizenTool("legal-aid") : undefined} role={role} question={message.role === "assistant" ? messages.slice(0, index).reverse().find(item => item.role === "user")?.content : undefined} onEdit={!loading && !message.documents?.some(document => !document.pages.length) ? (text) => void submit(text, message.documents, false, index) : undefined} onForgetDocuments={() => { const ids = new Set(message.documents?.map(document => document.id)); const clear = (items: ChatMessage[]) => items.map(item => ({...item, documents: item.documents?.map(document => ids.has(document.id) ? {...document, pages: []} : document)})); setMessages(clear); setHistory(current => current.map(item => ({...item, messages: clear(item.messages)}))); }} onRegenerate={!loading && message.role === "assistant" && index === messages.length-1 ? () => { const question=messages.slice(0,index).reverse().find(item=>item.role==="user"); if(question) void submit(question.content, question.documents, true); } : undefined} /></div>)}</div>
          {awayFromLatest && <button className="jump-latest" aria-label="Jump to latest message" onClick={() => window.scrollTo({ top: document.documentElement.scrollHeight, behavior: animate ? "smooth" : "auto" })}><ArrowDown size={17}/></button>}
          <div className="conversation-composer"><ChatInput key={`${sessionId}:${draftVersion}`} onSend={submit} onStop={stopResearch} loading={loading} mode={responseMode} onModeChange={setResponseMode} cases={chatCases} caseId={chatCaseId} onCaseChange={setChatCaseId} scopeLockedReason={scopeLockedReason(sessionId)} redactBeforeAttach={role === "citizen"} initialDraft={restoredDraft} /></div>
        </>}
      </section>}
    </div>
    {historyPanelOpen && <HistoryPanel onClose={() => setHistoryPanelOpen(false)} onOpen={openFromPanel} onChanged={() => setHistoryVersion(value => value + 1)} />}
    {accountOpen && <AccountDialog user={user} onClose={() => setAccountOpen(false)} onUserChange={setUser} onSignOut={() => { setAccountOpen(false); void signOut(); }} onErased={(receipt) => { setAccountOpen(false); setUser(null); setErasedReceipt(receipt); }} />}
    <AccountGate user={user} onCleared={() => setHistoryVersion(value => value + 1)} onSignOut={() => void signOut()} onOpenAccount={() => setAccountOpen(true)} />
    <CitizenGuideDialog open={citizenGuideSlide !== null} initialSlide={citizenGuideSlide ?? 0} onClose={() => setCitizenGuideSlide(null)} onStart={(prompt) => { setCitizenGuideSlide(null); void submit(prompt); }}/>
    {settingsOpen && <div className="modal-backdrop" onMouseDown={() => setSettingsOpen(false)}><div ref={settingsRef} role="dialog" aria-modal="true" aria-label="Settings" className="settings-dialog" onMouseDown={event => event.stopPropagation()}>
      <div className="dialog-heading settings-heading"><div><h2>Settings</h2><p>Make the workspace feel right for you.</p></div><button aria-label="Close settings" className="icon-button" onClick={() => setSettingsOpen(false)}><X size={18} /></button></div>
      <div className="settings-account"><div><strong>{user.name}</strong><span>{user.email}</span></div><b>{role}</b></div>
      <button className="settings-account-link" onClick={() => { setSettingsOpen(false); setAccountOpen(true); }}><span>Account and privacy<small>Password, two-step sign-in, devices, your data, text size</small></span><ChevronRight size={16} aria-hidden="true" /></button>
      <section className="settings-section"><h3>Experience</h3>
        <div className="setting-block"><div className="setting-copy"><strong>Appearance</strong><small>A calm palette for daytime or low light.</small></div><div className="theme-choice" role="group" aria-label="Appearance"><button aria-pressed={theme === "paper"} onClick={() => setTheme("paper")}><i className="paper-swatch"/>Light</button><button aria-pressed={theme === "ink"} onClick={() => setTheme("ink")}><i className="ink-swatch"/>Dark</button></div></div>
        <div className="setting-block setting-stack"><div className="setting-copy"><strong>Default research depth</strong><small>You can still change this beside any question.</small></div><div className="mode-choice" role="group" aria-label="Default response mode">{(["auto","fast","deep"] as RequestedResponseMode[]).map(mode => <button key={mode} aria-pressed={responseMode === mode} onClick={() => setResponseMode(mode)}>{mode === "auto" ? "Auto" : mode === "fast" ? "Fast" : "Deep review"}</button>)}</div></div>
        <label className="setting-block"><span className="setting-copy"><strong>Ambient motion</strong><small>Includes the scales and subtle background glow.</small></span><span className="premium-switch"><input type="checkbox" checked={animate} onChange={event => setAnimate(event.target.checked)} /><i/></span></label>
      </section>
      <section className="settings-section"><h3>History & privacy</h3>
        <label className="setting-block"><span className="setting-copy"><strong>Show recent chats</strong><small>Your conversations are stored on the server for your account. Delete one from its menu to erase it.</small></span><span className="premium-switch"><input type="checkbox" checked={rememberHistory} onChange={event => setRememberHistory(event.target.checked)} /><i/></span></label>
        <details className="settings-privacy"><summary>Documents, voice & retention<span>View details</span></summary><UploadPrivacy/><p>Voice uses your browser’s recognition service. English is currently validated; transcripts remain editable and never send automatically.</p></details>
      </section>
      <section className="settings-section"><h3>Corpus connection</h3><div className="corpus-status"><span className={progress?.validation_status === "pass" ? "is-online" : ""}/><div><strong>{progress?.validation_status === "pass" ? "Verified corpus ready" : "Corpus status unavailable"}</strong><small>{progress ? `${progress.canonical_documents.toLocaleString()} sources · ${(progress.global_points ?? progress.qdrant_points).toLocaleString()} searchable passages` : "Reconnect to check source availability."}</small></div></div></section>
      <div className="settings-actions"><button disabled={loading} onClick={() => { setHistory([]); setMessages([]); setSessionId(null); setActiveChatId(crypto.randomUUID()); setDraftVersion(value => value + 1); }}>Clear this tab’s history</button><button disabled={loading} onClick={() => { setSettingsOpen(false); void signOut(); }}><LogOut size={15} />Sign out</button></div>
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
