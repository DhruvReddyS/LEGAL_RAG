"use client";
import { ArrowUpRight, CircleAlert } from "lucide-react";
import { currencyView, safeSourceUrl } from "@/lib/source-preview";
import type { AgentCitation } from "@/lib/types";
import { useCitizenLang } from "./useCitizenLang";

/** F11: what replaced this source, shown where the legal note sends the reader. */
export default function SourceCurrency({ source, citizen = false }: { source: AgentCitation; citizen?: boolean }) {
  const { t } = useCitizenLang(citizen);
  const view = currencyView(source);
  const url = safeSourceUrl(source.source_url);
  return <>
    {view.kind === "repealed" && <div className="ctz-currency is-repealed" role="note">
      <CircleAlert size={15} aria-hidden="true"/>
      <div>
        <strong>{t("sourceRepealed")}{view.repealedOn ? ` ${t("sourceRepealedFrom")} ${view.repealedOn}` : ""}</strong>
        <p>{view.replacedBy ? `${t("sourceReplacedBy")} ${view.replacedBy}. ` : ""}{t("sourceMayApply")}</p>
      </div>
    </div>}
    {view.kind === "moved" && <div className="ctz-currency" role="note">
      <CircleAlert size={15} aria-hidden="true"/>
      <div>
        <strong>{t("sourceMoved")}</strong>
        {!!view.mappings?.length && <ul>{view.mappings.map(mapping => <li key={`${mapping.from_code}-${mapping.from_section}-${mapping.to_section}`}>
          {mapping.from_code} s.{mapping.from_section} → {mapping.to_code} s.{mapping.to_section}{mapping.subject ? ` (${mapping.subject})` : ""}
          {mapping.ingredients_changed && <em> {t("sourceElements")}</em>}
        </li>)}</ul>}
        {!!view.unmapped.length && <p>{t("sourceNoMapping")} {view.unmapped.join(", ")}. {t("sourceCheckAct")}</p>}
        {view.pendingReview && <p>{t("sourcePendingReview")}</p>}
      </div>
    </div>}
    {url && <a className="ctz-source-link" href={url} target="_blank" rel="noreferrer">{t("openOfficialSource")}<ArrowUpRight size={13} aria-hidden="true"/></a>}
  </>;
}
