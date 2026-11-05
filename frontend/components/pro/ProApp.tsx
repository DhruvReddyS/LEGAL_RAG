"use client";

import { ArrowRight, BookOpenText, BriefcaseBusiness, CalendarClock, CircleHelp, Eye, FileText, Fingerprint, LayoutDashboard, Loader2, Menu, MessageSquare, Search, Settings, X } from "lucide-react";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import BrandLogo from "@/components/BrandLogo";
import { useMyUnits } from "@/components/police/SupervisorView";
import { useDialogFocus } from "@/components/useDialogFocus";
import { ApiError, createCase, listCases } from "@/lib/api";
import { calendarAcrossCases } from "@/lib/api-advocate";
import { getRegister } from "@/lib/api-police";
import { supervisedUnits } from "@/lib/police-presentation";
import { dueFromCalendar, dueFromRegister } from "@/lib/pro-due";
import { countBuckets, type DueItem } from "@/lib/pro-presentation";
import { proHref, type ProRoute } from "@/lib/pro-route";
import type { LegalCase, User } from "@/lib/types";
import { ProLink, ProProvider, RowsLoading, usePro, type LoadState, type ProChatRow, type ProContextValue } from "./context";

const Loading = () => <RowsLoading label="Loading" rows={4} />;
const Dashboard = dynamic(() => import("./Dashboard"), { loading: Loading });
const CasesScreen = dynamic(() => import("./CasesScreen"), { loading: Loading });
const CasePage = dynamic(() => import("./CasePage"), { loading: Loading });
const DeadlinesScreen = dynamic(() => import("./DeadlinesScreen"), { loading: Loading });
const DraftsScreen = dynamic(() => import("./DraftsScreen"), { loading: Loading });
const ResearchScreen = dynamic(() => import("./ResearchScreen"), { loading: Loading });
const LawScreen = dynamic(() => import("./LawScreen"), { loading: Loading });
const UnitScreen = dynamic(() => import("./UnitScreen"), { loading: Loading });
const HelpScreen = dynamic(() => import("./HelpScreen"), { loading: Loading });

/** A chat screen is told which scope it is, and the page keeps the conversation. */
export type ChatView = (scope: { caseId: string | null; caseTitle?: string }) => ReactNode;

function NewCaseDialog({ onClose }: { onClose: () => void }) {
  const { isPolice, noun, navigate, replaceCase } = usePro();
  const ref = useDialogFocus(true, onClose);
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  const ready = title.trim().length >= 3;
  const submit = async () => {
    if (!ready || busy) return;
    setBusy(true); setFailure("");
    try {
      const created = await createCase(title.trim());
      replaceCase(created);
      onClose();
      navigate({ section: "case", caseId: created.id });
    } catch (error) {
      setFailure(error instanceof ApiError ? error.message : "The case could not be created. Check the connection and try again.");
      setBusy(false);
    }
  };
  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <div ref={ref} role="dialog" aria-modal="true" aria-label={`New ${noun}`} className="pro-dialog" onMouseDown={(event) => event.stopPropagation()}>
        <div className="pro-dialog-head">
          <h2>New {noun}</h2>
          <button type="button" className="icon-button" aria-label="Close" onClick={onClose}><X size={18} /></button>
        </div>
        <form onSubmit={(event) => { event.preventDefault(); void submit(); }}>
          <label className="pro-label">{isPolice ? "Investigation title" : "Case title"}
            <input autoFocus className="field" value={title} maxLength={255} placeholder={isPolice ? "For example, Theft at Market Road" : "For example, State v. Sharma"} onChange={(event) => setTitle(event.target.value)} />
          </label>
          <p className="pro-hint">Only you can read this {noun} and the files you add to it. You can rename it later.</p>
          {failure && <p className="pro-form-error" role="alert">{failure}</p>}
          <div className="pro-dialog-actions">
            <button type="button" className="pro-button" onClick={onClose}>Cancel</button>
            <button type="submit" className="pro-button is-primary" disabled={!ready || busy}>
              {busy && <Loader2 size={15} className="animate-spin" aria-hidden="true" />}Create {noun}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function NavItem({ to, icon: Icon, label, badge, onClose }: { to: ProRoute; icon: typeof Search; label: string; badge?: number; onClose: () => void }) {
  const { route } = usePro();
  return (
    <ProLink to={to} className="pro-nav-item" current={route.section === to.section || (to.section === "cases" && route.section === "case")} onNavigate={onClose}>
      <Icon size={17} strokeWidth={1.7} aria-hidden="true" />
      <span className="min-w-0 flex-1 truncate">{label}</span>
      {!!badge && <b className="pro-nav-badge" aria-label={`${badge} overdue`}>{badge}</b>}
    </ProLink>
  );
}

function Navigation({ onSettings, onSearchChats, onClose, closeRef, supervises }: {
  onSettings: () => void;
  onSearchChats: () => void;
  onClose: () => void;
  closeRef: React.RefObject<HTMLButtonElement>;
  supervises: boolean;
}) {
  const { user, isPolice, nounPlural, route, due, cases } = usePro();
  const counts = useMemo(() => countBuckets(due), [due]);
  const urgent = counts.act_now;
  const openCase = route.section === "case" ? cases.find((item) => item.id === route.caseId) : undefined;
  return (
    <>
      <div className="pro-brand">
        <BrandLogo />
        <button ref={closeRef} type="button" className="icon-button pro-only-compact" onClick={onClose} aria-label="Close navigation"><X size={18} /></button>
      </div>
      <p className="pro-role-chip">{isPolice ? "Police" : "Advocate"}</p>
      <nav aria-label="Main sections" className="pro-nav">
        <NavItem onClose={onClose} to={{ section: "dashboard" }} icon={LayoutDashboard} label="Dashboard" />
        <NavItem onClose={onClose} to={{ section: "cases" }} icon={isPolice ? Fingerprint : BriefcaseBusiness} label={nounPlural} />
        {openCase && (
          <ProLink to={{ section: "case", caseId: openCase.id, tab: route.tab, tool: route.tool }} className="pro-nav-open" current onNavigate={onClose}>
            <span className="truncate">{openCase.title}</span>
          </ProLink>
        )}
        <NavItem onClose={onClose} to={{ section: "deadlines" }} icon={CalendarClock} label={isPolice ? "Deadlines" : "Calendar"} badge={urgent} />
        <NavItem onClose={onClose} to={{ section: "drafts" }} icon={FileText} label="Drafts" />
        <NavItem onClose={onClose} to={{ section: "research" }} icon={MessageSquare} label="Research" />
        <NavItem onClose={onClose} to={{ section: "law" }} icon={BookOpenText} label="Law lookup" />
        {supervises && <NavItem onClose={onClose} to={{ section: "unit" }} icon={Eye} label="Unit supervision" />}
      </nav>
      <div className="pro-nav-bottom">
        <button type="button" className="pro-nav-item" onClick={() => { onClose(); onSearchChats(); }}><Search size={17} strokeWidth={1.7} aria-hidden="true" /><span>Search chats</span></button>
        <NavItem onClose={onClose} to={{ section: "help" }} icon={CircleHelp} label="Help" />
        <button type="button" className="pro-nav-item" onClick={() => { onClose(); onSettings(); }}>
          <Settings size={17} strokeWidth={1.7} aria-hidden="true" />
          <span className="min-w-0 flex-1 truncate">Settings</span>
        </button>
        <p className="pro-nav-user" title={user.email}>{user.name}</p>
      </div>
    </>
  );
}

const SECTION_TITLES: Partial<Record<ProRoute["section"], string>> = {
  dashboard: "Dashboard",
  deadlines: "Deadlines",
  drafts: "Drafts",
  research: "Research",
  law: "Law lookup",
  unit: "Unit supervision",
  help: "Help",
};

/**
 * The application a police officer or an advocate signs in to: one navigation, and
 * one screen with one job at a time. The conversation stays in the page above this,
 * which is what lets a Deep review carry on while the person works elsewhere.
 */
export default function ProApp({ user, route, navigate, chats, onCasesChange, onOpenChat, chatView, busyScope, onSettings, onSearchChats }: {
  user: User;
  route: ProRoute;
  navigate: ProContextValue["navigate"];
  chats: ProChatRow[];
  onCasesChange: (cases: LegalCase[]) => void;
  onOpenChat: (id: string) => void;
  chatView: ChatView;
  /** A question still being answered, and which screen it belongs on. */
  busyScope: { caseId: string | null } | null;
  onSettings: () => void;
  onSearchChats: () => void;
}) {
  const isPolice = user.role === "police";
  const noun = isPolice ? "investigation" : "case";
  const nounPlural = isPolice ? "Investigations" : "Cases";

  const [cases, setCases] = useState<LegalCase[]>([]);
  const [casesState, setCasesState] = useState<LoadState>("loading");
  const reloadCases = useCallback(() => {
    setCasesState("loading");
    listCases().then((response) => { setCases(response.cases); setCasesState("ready"); }).catch(() => setCasesState("failed"));
  }, []);
  useEffect(() => { reloadCases(); }, [reloadCases]);
  useEffect(() => { onCasesChange(cases); }, [cases, onCasesChange]);
  const replaceCase = useCallback((updated: LegalCase) => {
    setCases((current) => [updated, ...current.filter((item) => item.id !== updated.id)]);
    setCasesState("ready");
  }, []);

  const [due, setDue] = useState<DueItem[]>([]);
  const [dueState, setDueState] = useState<LoadState>("loading");
  const [casesWithoutFacts, setWithoutFacts] = useState<{ case_id: string; title: string }[]>([]);
  // Quiet: a refresh must not blank a list the person is reading. Only a first read shows as loading.
  const loadDue = useCallback(async () => {
    try {
      if (isPolice) {
        const register = await getRegister();
        const now = Date.parse(register.evaluated_at) || Date.now();
        setDue(register.rows.map((row) => dueFromRegister(row, now)));
        setWithoutFacts(register.cases_without_facts);
      } else {
        const calendar = await calendarAcrossCases();
        setDue(calendar.events.map((event) => dueFromCalendar(event)));
      }
      setDueState("ready");
    } catch {
      setDueState("failed");
    }
  }, [isPolice]);
  const reloadDue = useCallback(() => { void loadDue(); }, [loadDue]);
  // What is due can change on any tool's screen, so the overviews read it again on arrival.
  const needsFreshDue = route.section === "dashboard" || route.section === "cases" || route.section === "case";
  useEffect(() => { if (needsFreshDue) void loadDue(); }, [needsFreshDue, loadDue]);

  const activity = useMemo(() => {
    const latest = new Map<string, number>();
    for (const chat of chats) if (chat.caseId) latest.set(chat.caseId, Math.max(latest.get(chat.caseId) ?? 0, chat.updatedAt));
    return latest;
  }, [chats]);

  const [newCase, setNewCase] = useState(false);
  const units = useMyUnits(isPolice);
  const supervises = supervisedUnits(units).length > 0;
  const value: ProContextValue = {
    user, isPolice, noun, nounPlural, route, navigate, cases, casesState, reloadCases, replaceCase,
    due, dueState, reloadDue, casesWithoutFacts, activity, chats, openChat: onOpenChat, openNewCase: () => setNewCase(true), units,
  };

  // The drawer is inert until it opens, so focus is moved into it by hand.
  const [drawer, setDrawer] = useState(false);
  const [compact, setCompact] = useState(false);
  const openRef = useRef<HTMLButtonElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const drawerWasOpen = useRef(false);
  useEffect(() => {
    const media = window.matchMedia("(max-width: 1023px)");
    const update = () => setCompact(media.matches);
    update(); media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    if (drawer) closeRef.current?.focus();
    else if (drawerWasOpen.current && !document.querySelector("[role='dialog']")) openRef.current?.focus();
    drawerWasOpen.current = drawer;
  }, [drawer]);
  useEffect(() => {
    if (!drawer) return;
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") setDrawer(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawer]);

  // Arriving on a new screen moves the reader to its top, and the keyboard to its heading.
  // The open conversation joins the address as its first answer arrives: not a new screen.
  const href = proHref({ ...route, chat: undefined });
  const screenKey = `${route.section}:${route.caseId ?? ""}`;
  const shownHref = useRef(href);
  const shownScreen = useRef(screenKey);
  const mainRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (shownHref.current === href) return;
    shownHref.current = href;
    window.scrollTo({ top: 0, behavior: "auto" });
    if (shownScreen.current !== screenKey) {
      shownScreen.current = screenKey;
      if (!drawer) mainRef.current?.focus({ preventScroll: true });
    }
  }, [href, screenKey, drawer]);

  const openCaseTitle = route.section === "case" ? cases.find((item) => item.id === route.caseId)?.title : undefined;
  const screenTitle = route.section === "cases" ? nounPlural : route.section === "case" ? openCaseTitle ?? nounPlural : (route.section === "deadlines" && !isPolice ? "Calendar" : SECTION_TITLES[route.section]);
  useEffect(() => { if (screenTitle) document.title = `${screenTitle} | Corpusil`; }, [screenTitle]);

  // The last case opened stays mounted while the person looks elsewhere, so a half-typed
  // narrative survives a look at the dashboard. Its key means another case replaces it whole.
  const [lastCaseId, setLastCaseId] = useState<string | null>(route.section === "case" ? route.caseId ?? null : null);
  useEffect(() => { if (route.section === "case" && route.caseId) setLastCaseId(route.caseId); }, [route.section, route.caseId]);
  const shownCaseId = route.section === "case" ? route.caseId ?? null : lastCaseId;

  const onChatScreen = busyScope && (
    (route.section === "research" && busyScope.caseId === null)
    || (route.section === "case" && route.tab === "ask" && route.caseId === busyScope.caseId)
  );

  return (
    <ProProvider value={value}>
      <div className="pro-app" data-pro-role={isPolice ? "police" : "advocate"}>
        <a className="skip-link" href="#pro-main">Skip to content</a>
        <aside
          aria-label="Main navigation"
          aria-hidden={compact && !drawer ? true : undefined}
          ref={(node) => { if (node) node.inert = compact && !drawer; }}
          className={`pro-sidebar ${drawer ? "is-open" : ""}`}
        >
          <Navigation onSettings={onSettings} onSearchChats={onSearchChats} onClose={() => setDrawer(false)} closeRef={closeRef} supervises={supervises} />
        </aside>
        {drawer && <button type="button" tabIndex={-1} aria-label="Dismiss navigation" className="sidebar-scrim" onClick={() => setDrawer(false)} />}
        <div className="pro-content" ref={(node) => { if (node) node.inert = compact && drawer; }}>
          <div className="pro-topbar">
            <button ref={openRef} type="button" className="icon-button" aria-label="Open navigation" onClick={() => setDrawer(true)}><Menu size={20} /></button>
            <span>Corpusil</span><span className="pro-role-chip">{isPolice ? "Police" : "Advocate"}</span>
          </div>
          {busyScope && !onChatScreen && (
            <div className="pro-strip" role="status">
              <Loader2 size={14} className="animate-spin" aria-hidden="true" />
              <span className="min-w-0 flex-1">An answer is still being prepared. You can keep working.</span>
              <ProLink to={busyScope.caseId ? { section: "case", caseId: busyScope.caseId, tab: "ask" } : { section: "research" }}>Open it<ArrowRight size={13} aria-hidden="true" /></ProLink>
            </div>
          )}
          <div id="pro-main" className="pro-main" tabIndex={-1} ref={mainRef}>
            {route.section === "dashboard" && <Dashboard />}
            {route.section === "cases" && <CasesScreen />}
            {shownCaseId && (
              <CasePage key={shownCaseId} caseId={shownCaseId} active={route.section === "case"} chatView={chatView} />
            )}
            {route.section === "deadlines" && <DeadlinesScreen />}
            {route.section === "drafts" && <DraftsScreen />}
            {route.section === "research" && <ResearchScreen chatView={chatView} />}
            {route.section === "law" && <LawScreen />}
            {route.section === "unit" && <UnitScreen units={units} />}
            {route.section === "help" && <HelpScreen />}
          </div>
          <p className="pro-foot">Information for your professional review, not legal advice.</p>
        </div>
        {newCase && <NewCaseDialog onClose={() => setNewCase(false)} />}
      </div>
    </ProProvider>
  );
}

