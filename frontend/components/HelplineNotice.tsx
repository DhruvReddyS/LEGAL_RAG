"use client";
import { Phone } from "lucide-react";
import { useCitizenLang } from "./citizen/useCitizenLang";
import type { HelplineContact } from "@/lib/types";

export function HelplineNotice({ contacts }: { contacts: HelplineContact[] }) {
  const { t } = useCitizenLang();
  return <aside className="helpline-notice" role="status" aria-label={t("helplinesLabel")}>
    <p><strong>{t("helplineLead")}</strong> {t("helplineRest")}</p>
    <ul>{contacts.map(item => <li key={item.number}><a href={`tel:${item.number}`}><Phone size={13} aria-hidden="true"/>{item.label}: <strong>{item.number}</strong></a></li>)}</ul>
  </aside>;
}
