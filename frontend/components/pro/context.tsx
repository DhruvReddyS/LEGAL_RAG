"use client";

import { AlertTriangle, RefreshCw, type LucideIcon } from "lucide-react";
import { createContext, useContext, type MouseEvent, type ReactNode } from "react";
import type { DueItem } from "@/lib/pro-presentation";
import { proHref, type ProRoute } from "@/lib/pro-route";
import type { LegalCase, User } from "@/lib/types";
import type { MyUnit } from "@/lib/types-police";

export type LoadState = "loading" | "ready" | "failed";

/** A conversation, as the screens need it. Bodies stay with the chat. */
export interface ProChatRow { id: string; title: string; caseId: string | null; updatedAt: number }

export interface ProContextValue {
  user: User;
  isPolice: boolean;
  /** "investigation" or "case", as the person would say it. */
  noun: string;
  nounPlural: string;
  route: ProRoute;
  navigate: (to: ProRoute, options?: { replace?: boolean }) => void;
  cases: LegalCase[];
  casesState: LoadState;
  reloadCases: () => void;
  replaceCase: (updated: LegalCase) => void;
  due: DueItem[];
  dueState: LoadState;
  reloadDue: () => void;
  /** Police only: open cases the register has nothing recorded for. */
  casesWithoutFacts: { case_id: string; title: string }[];
  /** Last conversation per case. The server keeps no last-activity date of its own. */
  activity: Map<string, number>;
  chats: ProChatRow[];
  openChat: (id: string) => void;
  openNewCase: () => void;
  /** Police only: the units this officer belongs to. */
  units: MyUnit[];
}

const ProContext = createContext<ProContextValue | null>(null);
export const ProProvider = ProContext.Provider;

export function usePro(): ProContextValue {
  const value = useContext(ProContext);
  if (!value) throw new Error("usePro is only available inside the professional shell.");
  return value;
}

/** A real link, so a case opens in a new tab like any other, and the page does not reload for a plain click. */
export function ProLink({ to, className, children, current, label, onNavigate }: {
  to: ProRoute;
  className?: string;
  children: ReactNode;
  current?: boolean;
  label?: string;
  onNavigate?: () => void;
}) {
  const { navigate } = usePro();
  const click = (event: MouseEvent<HTMLAnchorElement>) => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    navigate(to);
    onNavigate?.();
  };
  return <a href={proHref(to)} className={className} aria-current={current ? "page" : undefined} aria-label={label} onClick={click}>{children}</a>;
}

export function PageHead({ title, lead, action, eyebrow }: { title: string; lead?: ReactNode; action?: ReactNode; eyebrow?: string }) {
  return (
    <header className="pro-page-head">
      <div className="min-w-0">
        {eyebrow && <p className="pro-eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {lead && <p className="pro-lead">{lead}</p>}
      </div>
      {action && <div className="pro-page-action">{action}</div>}
    </header>
  );
}

export function EmptyState({ icon: Icon, title, children, action }: { icon: LucideIcon; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="pro-empty">
      <span className="pro-empty-icon"><Icon size={20} aria-hidden="true" /></span>
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {action && <div className="pro-empty-action">{action}</div>}
    </div>
  );
}

export function ErrorState({ title, onRetry }: { title: string; onRetry?: () => void }) {
  return (
    <div className="pro-error" role="alert">
      <AlertTriangle size={16} aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <strong>{title}</strong>
        <span>Check the connection and try again. Nothing you saved has been lost.</span>
      </div>
      {onRetry && <button type="button" className="pro-button" onClick={onRetry}><RefreshCw size={14} aria-hidden="true" />Try again</button>}
    </div>
  );
}

export function RowsLoading({ label, rows = 3 }: { label: string; rows?: number }) {
  return (
    <div className="pro-skeleton" role="status" aria-label={label}>
      {Array.from({ length: rows }, (_, index) => <span key={index} />)}
    </div>
  );
}

export function StatusPill({ status }: { status: string }) {
  return <span className={`pro-pill is-${status}`}>{status.charAt(0).toUpperCase() + status.slice(1)}</span>;
}

export function DuePill({ item }: { item: Pick<DueItem, "status" | "tone"> }) {
  return <span className={`pro-pill tone-${item.tone}`}>{item.status}</span>;
}

/** One due item. The whole row opens the case at the place to act on it. */
export function DueRow({ item, to, showCase = true }: { item: DueItem; to: ProRoute; showCase?: boolean }) {
  return (
    <li>
      <ProLink to={to} className={`pro-due-row tone-${item.tone}`}>
        <span className="pro-due-main">
          <strong>{item.title}</strong>
          <span className="pro-meta">
            {showCase && item.caseTitle && <span className="pro-meta-case">{item.caseTitle}</span>}
            <span>{item.tag}</span>
          </span>
        </span>
        <span className="pro-due-when">
          <span>{item.when}</span>
          {item.relative && <small>{item.relative}</small>}
        </span>
        <DuePill item={item} />
      </ProLink>
    </li>
  );
}

export function Card({ title, action, children, id }: { title: string; action?: ReactNode; children: ReactNode; id?: string }) {
  return (
    <section className="pro-card" aria-labelledby={id}>
      <div className="pro-card-head">
        <h2 id={id}>{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}
