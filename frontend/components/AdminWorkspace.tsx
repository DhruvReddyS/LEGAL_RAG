"use client";

import { Activity, BarChart3, BookOpenCheck, Cpu, Gauge, LockKeyhole, Rocket, Siren, Timer, UsersRound } from "lucide-react";
import { KeyboardEvent, useCallback, useEffect, useRef, useState } from "react";
import AuditPanel from "./admin/AuditPanel";
import CorpusPanel from "./admin/CorpusPanel";
import IncidentsPanel from "./admin/IncidentsPanel";
import ModelsPanel from "./admin/ModelsPanel";
import OverviewPanel from "./admin/OverviewPanel";
import QualityPanel from "./admin/QualityPanel";
import ReleasePanel from "./admin/ReleasePanel";
import RetentionPanel from "./admin/RetentionPanel";
import UsersPanel from "./admin/UsersPanel";

const TABS = [
  { key: "overview", label: "Overview", icon: Gauge },
  { key: "release", label: "Release", icon: Rocket },
  { key: "corpus", label: "Corpus", icon: BookOpenCheck },
  { key: "quality", label: "Quality", icon: BarChart3 },
  { key: "incidents", label: "Incidents", icon: Siren },
  { key: "users", label: "Users", icon: UsersRound },
  { key: "retention", label: "Retention", icon: Timer },
  { key: "models", label: "Models", icon: Cpu },
  { key: "audit", label: "Audit", icon: Activity },
] as const;

type TabKey = (typeof TABS)[number]["key"];

const STORAGE_KEY = "corpusil.admin.tab";

export default function AdminWorkspace() {
  const [tab, setTab] = useState<TabKey>("overview");
  const [prefillDocument, setPrefillDocument] = useState<string | null>(null);
  const buttons = useRef<Partial<Record<TabKey, HTMLButtonElement | null>>>({});

  useEffect(() => {
    try {
      const saved = window.sessionStorage.getItem(STORAGE_KEY);
      if (saved && TABS.some(item => item.key === saved)) setTab(saved as TabKey);
    } catch {
      // Storage can be unavailable. The console simply opens on Overview.
    }
  }, []);

  const choose = useCallback((next: TabKey) => {
    setTab(next);
    try { window.sessionStorage.setItem(STORAGE_KEY, next); } catch { /* see above */ }
  }, []);

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const index = TABS.findIndex(item => item.key === tab);
    const targets: Record<string, number> = {
      ArrowRight: (index + 1) % TABS.length,
      ArrowLeft: (index - 1 + TABS.length) % TABS.length,
      Home: 0,
      End: TABS.length - 1,
    };
    const target = targets[event.key];
    if (target === undefined) return;
    event.preventDefault();
    const next = TABS[target].key;
    choose(next);
    buttons.current[next]?.focus();
  };

  const clearPrefill = useCallback(() => setPrefillDocument(null), []);

  return (
    <section className="admin-console">
      <header className="admin-console-head">
        <div>
          <p className="eyebrow">Governance control plane</p>
          <h2>Administration</h2>
          <p>Decide releases, keep the corpus honest, handle incidents and account for every sensitive action.</p>
        </div>
        <div className="admin-rbac">
          <LockKeyhole size={13} aria-hidden="true" /> Private case material is not searchable here
        </div>
      </header>

      <div className="admin-tabs" role="tablist" aria-label="Administration sections" onKeyDown={onKeyDown}>
        {TABS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            ref={element => { buttons.current[key] = element; }}
            role="tab"
            id={`admin-tab-${key}`}
            aria-selected={tab === key}
            aria-controls={`admin-panel-${key}`}
            tabIndex={tab === key ? 0 : -1}
            onClick={() => choose(key)}
          >
            <Icon size={14} aria-hidden="true" /> {label}
          </button>
        ))}
      </div>

      <div role="tabpanel" id={`admin-panel-${tab}`} aria-labelledby={`admin-tab-${tab}`} className="admin-tabpanel">
        {tab === "overview" && <OverviewPanel />}
        {tab === "release" && <ReleasePanel />}
        {tab === "corpus" && <CorpusPanel onQuarantine={documentId => { setPrefillDocument(documentId); choose("incidents"); }} />}
        {tab === "quality" && <QualityPanel />}
        {tab === "incidents" && <IncidentsPanel prefillDocument={prefillDocument} onPrefillUsed={clearPrefill} />}
        {tab === "users" && <UsersPanel />}
        {tab === "retention" && <RetentionPanel />}
        {tab === "models" && <ModelsPanel />}
        {tab === "audit" && <AuditPanel />}
      </div>
    </section>
  );
}
