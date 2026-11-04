"use client";
import { CalendarDays, CalendarPlus, Check, Trash2, Undo2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { ApiError } from "@/lib/api";
import { createDeadline, deleteDeadline, listDeadlines, updateDeadline } from "@/lib/api-citizen";
import { buildIcs, dueLabel } from "@/lib/citizen-matter";
import { UI } from "@/lib/citizen-i18n";
import { l, type Lang } from "@/lib/citizen-law/law";
import type { CitizenDeadline, DeadlineDraft } from "@/lib/types-citizen";
import { downloadText } from "./shared";
import { useCitizenLang } from "./useCitizenLang";

const DAYS = {
  left: (days: number, lang: Lang) => ({ en: `${days} ${days === 1 ? "day" : "days"} left`, hi: `${days} दिन बाकी`, te: `${days} రోజులు మిగిలాయి` })[lang],
  over: (days: number, lang: Lang) => ({ en: `${days} ${days === 1 ? "day" : "days"} overdue`, hi: `${days} दिन बीत गए`, te: `${days} రోజులు దాటాయి` })[lang],
};
const STATUS_ORDER = l("Overdue dates need a person now", "बीत चुकी तारीखों के लिए अभी किसी व्यक्ति से बात करें", "దాటిన తేదీలకు ఇప్పుడే ఒక వ్యక్తితో మాట్లాడండి");

export default function MyMatter({ draft, onChange }: { draft?: DeadlineDraft | null; onChange?: (items: CitizenDeadline[]) => void }) {
  const { lang, t } = useCitizenLang();
  const [items, setItems] = useState<CitizenDeadline[] | null>(null);
  const [error, setError] = useState("");
  const [title, setTitle] = useState(draft?.title ?? "");
  const [dueOn, setDueOn] = useState(draft?.due_on ?? "");
  const [remind, setRemind] = useState(7);
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [origin, setOrigin] = useState<Pick<DeadlineDraft, "source" | "provision_label">>({ source: draft?.source ?? "manual", provision_label: draft?.provision_label ?? null });

  useEffect(() => { if (draft) { setTitle(draft.title); setDueOn(draft.due_on); setOrigin({ source: draft.source ?? "manual", provision_label: draft.provision_label ?? null }); } }, [draft]);

  const refresh = useCallback(async () => {
    try { const response = await listDeadlines(); setItems(response.items); onChange?.(response.items); setError(""); }
    catch { setItems(current => current ?? []); setError(UI.couldNotLoad[lang]); }
  }, [lang, onChange]);
  useEffect(() => { void refresh(); }, [refresh]);

  const fail = (cause: unknown) => setError(cause instanceof ApiError ? cause.message : t("somethingWrong"));
  const add = async () => {
    if (!title.trim() || !dueOn) { setError(t("needTitleDate")); return; }
    setBusy(true); setError("");
    try {
      await createDeadline({ title: title.trim(), due_on: dueOn, remind_days_before: remind, notes: notes.trim() || null, ...origin });
      setTitle(""); setDueOn(""); setNotes(""); setRemind(7); setOrigin({ source: "manual", provision_label: null });
      await refresh();
    } catch (cause) { fail(cause); } finally { setBusy(false); }
  };
  const toggle = async (item: CitizenDeadline) => { try { await updateDeadline(item.id, { completed: !item.completed_at }); await refresh(); } catch (cause) { fail(cause); } };
  const remove = async (item: CitizenDeadline) => { try { await deleteDeadline(item.id); await refresh(); } catch (cause) { fail(cause); } };

  return <div className="ctz-matter">
    <p className="ctz-lead">{t("matterLead")}</p>
    <form className="ctz-form ctz-matter-form" onSubmit={event => { event.preventDefault(); void add(); }}>
      <label className="ctz-field is-wide" htmlFor="matter-title"><span>{t("matterNewTitle")}</span><input id="matter-title" className="field" maxLength={200} value={title} onChange={event => setTitle(event.target.value)}/></label>
      <label className="ctz-field" htmlFor="matter-date"><span>{t("matterDue")}</span><input id="matter-date" className="field" type="date" value={dueOn} onChange={event => setDueOn(event.target.value)}/></label>
      <label className="ctz-field" htmlFor="matter-remind"><span>{t("matterRemind")}</span><input id="matter-remind" className="field" type="number" min={0} max={90} value={remind} onChange={event => setRemind(Math.min(90, Math.max(0, Number(event.target.value) || 0)))}/></label>
      <label className="ctz-field is-wide" htmlFor="matter-notes"><span>{t("matterNotes")}</span><textarea id="matter-notes" className="field ctz-textarea" rows={2} maxLength={2000} value={notes} onChange={event => setNotes(event.target.value)}/></label>
      {origin.provision_label && <p className="ctz-note is-wide">{t("matterBasis")}: <span lang="en">{origin.provision_label}</span></p>}
      <div className="ctz-actions is-wide"><button type="submit" className="button-primary ctz-primary" disabled={busy}>{t("matterAdd")}</button></div>
    </form>
    {error && <p className="ctz-error" role="alert">{error}</p>}
    <p className="ctz-note">{t("matterCalendarHint")}</p>
    {items === null ? <p className="ctz-working" role="status">{t("loading")}</p> : !items.length ? <div className="ctz-empty"><CalendarDays size={22} aria-hidden="true"/><p>{t("matterEmpty")}</p></div> :
      <ul className="ctz-dates">{items.map(item => <li key={item.id} className="ctz-date" data-status={item.status}>
        <div className="ctz-date-main">
          <strong className="ctz-date-title">{item.title}</strong>
          <span className="ctz-date-when">{item.due_on}</span>
          <span className="ctz-date-state">{dueLabel(item, { done: t("matterDone"), today: t("matterToday"), overdue: days => DAYS.over(days, lang), left: days => DAYS.left(days, lang) })}</span>
          {item.status === "overdue" && <p className="ctz-note">{STATUS_ORDER[lang]}</p>}
          {item.provision_label && <span className="ctz-note">{t("matterBasis")}: <span lang="en">{item.provision_label}</span></span>}
          {item.notes && <p className="ctz-note">{item.notes}</p>}
        </div>
        <div className="ctz-date-actions">
          <button type="button" className="ctz-icon-btn" onClick={() => void toggle(item)} aria-label={`${item.completed_at ? t("matterUndo") : t("matterMarkDone")}: ${item.title}`}>{item.completed_at ? <Undo2 size={16} aria-hidden="true"/> : <Check size={16} aria-hidden="true"/>}</button>
          <button type="button" className="ctz-icon-btn" onClick={() => downloadText(`corpusil-date-${item.due_on}.ics`, buildIcs(item), "text/calendar;charset=utf-8")} aria-label={`${t("matterCalendar")}: ${item.title}`}><CalendarPlus size={16} aria-hidden="true"/></button>
          <button type="button" className="ctz-icon-btn" onClick={() => void remove(item)} aria-label={`${t("remove")}: ${item.title}`}><Trash2 size={16} aria-hidden="true"/></button>
        </div>
      </li>)}</ul>}
  </div>;
}
