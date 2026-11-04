"use client";

import { Check, FolderOpen, Loader2, Pin, PinOff, Search, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useDialogFocus } from "@/components/useDialogFocus";
import { ApiError } from "@/lib/api";
import { listHistorySessions, listMatters, searchHistory, setSessionMatter, setSessionPinned } from "@/lib/api-platform";
import { debounce, formatRelativeDay, mergeById, normalizeMatter } from "@/lib/history-view";
import { bandwidthPlan, readPreferences } from "@/lib/preferences";
import type { HistorySession, MatterCount } from "@/lib/types-platform";

/**
 * Find a conversation, and organise it. Everything happens on the server, so it
 * reaches past the thirty the sidebar first loads, and it follows the person to
 * their other devices.
 */
export default function HistoryPanel({ onClose, onOpen, onChanged }: { onClose: () => void; onOpen: (item: HistorySession) => void; onChanged: () => void }) {
  const ref = useDialogFocus(true, onClose);
  const [term, setTerm] = useState("");
  const [matter, setMatter] = useState<string>("");
  const [items, setItems] = useState<HistorySession[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [matters, setMatters] = useState<MatterCount[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const latest = useRef(0);
  const pageSize = bandwidthPlan(readPreferences().lowBandwidth).historyPageSize;

  const load = useCallback(async (searchTerm: string, matterName: string, after: string | null) => {
    const request = ++latest.current;
    setLoading(true);
    setError("");
    try {
      const page = searchTerm.trim().length >= 2
        ? await searchHistory(searchTerm.trim(), after, pageSize)
        : await listHistorySessions({ limit: pageSize, cursor: after, matter: matterName || null });
      if (request !== latest.current) return;
      const visible = searchTerm.trim().length >= 2 && matterName
        ? page.items.filter(item => item.matter === matterName)
        : page.items;
      setItems(current => (after ? mergeById(current, visible) : visible));
      setCursor(page.next_cursor);
    } catch (failure) {
      if (request === latest.current) setError(failure instanceof ApiError ? failure.message : "Your conversations could not be loaded.");
    } finally {
      if (request === latest.current) setLoading(false);
    }
  }, [pageSize]);

  const refreshMatters = useCallback(() => { listMatters().then(setMatters).catch(() => setMatters([])); }, []);
  useEffect(refreshMatters, [refreshMatters]);

  const debounced = useMemo(() => debounce(load, 300), [load]);
  useEffect(() => {
    debounced(term, matter, null);
    return () => debounced.cancel();
  }, [term, matter, debounced]);

  const togglePin = async (item: HistorySession) => {
    setError("");
    try {
      await setSessionPinned(item.id, !item.pinned);
      setItems(current => current.map(row => (row.id === item.id ? { ...row, pinned: !item.pinned } : row)));
      onChanged();
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "That could not be saved.");
    }
  };

  const saveMatter = async (item: HistorySession) => {
    const next = normalizeMatter(draft);
    setError("");
    try {
      await setSessionMatter(item.id, next);
      setItems(current => current.map(row => (row.id === item.id ? { ...row, matter: next } : row)));
      setEditing(null);
      refreshMatters();
      onChanged();
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "That could not be saved.");
    }
  };

  return (
    <div className="modal-backdrop acct-backdrop" onMouseDown={onClose}>
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby="history-title" className="acct-dialog history-dialog" onMouseDown={event => event.stopPropagation()}>
        <div className="acct-head">
          <h2 id="history-title">Your conversations</h2>
          <button type="button" className="icon-button" aria-label="Close conversations" onClick={onClose}><X size={18} /></button>
        </div>
        <div className="history-controls">
          <label className="history-search">
            <Search size={15} aria-hidden="true" />
            <span className="sr-only">Search your conversations</span>
            <input autoFocus type="search" placeholder="Search titles and messages" value={term} onChange={event => setTerm(event.target.value)} />
          </label>
          <label className="history-filter">
            <span className="sr-only">Filter by matter</span>
            <select value={matter} onChange={event => setMatter(event.target.value)}>
              <option value="">All matters</option>
              {matters.map(row => <option key={row.matter} value={row.matter}>{row.matter} ({row.count})</option>)}
            </select>
          </label>
        </div>
        {error && <p role="alert" className="auth-error">{error}</p>}
        <ul className="history-results" aria-live="polite" aria-busy={loading}>
          {items.map(item => (
            <li key={item.id}>
              <button type="button" className="history-open" onClick={() => onOpen(item)}>
                <strong>{item.title}</strong>
                {item.match_snippet && <span className="history-snippet">{item.match_snippet}</span>}
                <small>{formatRelativeDay(item.updated_at)} · {item.message_count} messages{item.matter ? ` · ${item.matter}` : ""}</small>
              </button>
              <div className="history-row-actions">
                <button type="button" className="icon-button" aria-pressed={item.pinned} aria-label={item.pinned ? `Unpin ${item.title}` : `Pin ${item.title}`} onClick={() => void togglePin(item)}>
                  {item.pinned ? <PinOff size={15} aria-hidden="true" /> : <Pin size={15} aria-hidden="true" />}
                </button>
                <button type="button" className="icon-button" aria-label={`Set matter for ${item.title}`} aria-expanded={editing === item.id} onClick={() => { setEditing(editing === item.id ? null : item.id); setDraft(item.matter ?? ""); }}>
                  <FolderOpen size={15} aria-hidden="true" />
                </button>
              </div>
              {editing === item.id && (
                <form className="history-matter" onSubmit={event => { event.preventDefault(); void saveMatter(item); }}>
                  <label>
                    <span className="sr-only">Matter name</span>
                    <input autoFocus list="history-matters" maxLength={120} placeholder="Matter name. Leave blank to clear." value={draft} onChange={event => setDraft(event.target.value)} onKeyDown={event => { if (event.key === "Escape") { event.stopPropagation(); setEditing(null); } }} />
                  </label>
                  <button className="icon-button" aria-label="Save matter"><Check size={15} aria-hidden="true" /></button>
                </form>
              )}
            </li>
          ))}
        </ul>
        <datalist id="history-matters">{matters.map(row => <option key={row.matter} value={row.matter} />)}</datalist>
        {!loading && !items.length && !error && <p className="acct-hint history-empty">{term.trim().length >= 2 ? "Nothing matched that." : "No conversations here yet."}</p>}
        <div className="history-foot">
          {loading && <span role="status" className="acct-hint"><Loader2 size={14} className="animate-spin inline" aria-hidden="true" /> Loading&hellip;</span>}
          {cursor && !loading && <button type="button" className="button-secondary" onClick={() => void load(term, matter, cursor)}>Show more</button>}
        </div>
      </div>
    </div>
  );
}
