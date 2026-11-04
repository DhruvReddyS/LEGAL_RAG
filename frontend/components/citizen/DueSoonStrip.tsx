"use client";
import { CalendarDays } from "lucide-react";
import { useEffect, useState } from "react";
import { listDeadlines } from "@/lib/api-citizen";
import { formatDate } from "@/lib/citizen-i18n";
import { needsAttention } from "@/lib/citizen-matter";
import type { CitizenDeadline } from "@/lib/types-citizen";
import { useCitizenLang } from "./useCitizenLang";

/** C-10 reminders where the person lands. A date only helps if it is seen. */
export default function DueSoonStrip({ onOpen }: { onOpen: () => void }) {
  const { lang, t } = useCitizenLang();
  const [items, setItems] = useState<CitizenDeadline[]>([]);
  useEffect(() => {
    let live = true;
    listDeadlines().then(response => { if (live) setItems(needsAttention(response.items)); }).catch(() => undefined);
    return () => { live = false; };
  }, []);
  if (!items.length) return null;
  return <section className="ctz-attention ctz-attention-chat" aria-label={t("attentionTitle")}>
    <h2><CalendarDays size={16} aria-hidden="true"/>{t("attentionTitle")}</h2>
    <ul>{items.slice(0, 3).map(item => <li key={item.id} data-status={item.status}><button type="button" onClick={onOpen}><span>{item.title}</span><b>{formatDate(item.due_on, lang)}</b></button></li>)}</ul>
  </section>;
}
