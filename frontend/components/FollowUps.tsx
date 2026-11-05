"use client";

import { CornerDownLeft } from "lucide-react";
import { useCitizenLang } from "@/components/citizen/useCitizenLang";
import { citizenFollowUps, FILL_COMPOSER_EVENT, professionalFollowUps } from "@/lib/follow-ups";
import type { AgentCitation } from "@/lib/types";

/** Questions someone might ask next. Choosing one fills the composer and sends nothing. */
export default function FollowUps({ citations, role, citizen }: { citations: AgentCitation[]; role?: string; citizen: boolean }) {
  const { t } = useCitizenLang(citizen);
  const questions = citizen ? citizenFollowUps(citations).map((key) => t(key)) : professionalFollowUps(role, citations);
  const fill = (text: string) => window.dispatchEvent(new CustomEvent(FILL_COMPOSER_EVENT, { detail: text }));
  return (
    <section className="follow-ups" aria-label={t("followUpsLabel")}>
      <h3>{t("followUpsLabel")}</h3>
      <ul>
        {questions.map((question) => (
          <li key={question}>
            <button type="button" onClick={() => fill(question)}>
              <CornerDownLeft size={13} aria-hidden="true" />{question}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
