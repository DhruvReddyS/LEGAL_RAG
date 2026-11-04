"use client";
import { ArrowUpRight, CircleAlert } from "lucide-react";
import { currencyView, safeSourceUrl } from "@/lib/source-preview";
import type { AgentCitation } from "@/lib/types";

/** F11: what replaced this source, shown where the legal note sends the reader. */
export default function SourceCurrency({ source }: { source: AgentCitation }) {
  const view = currencyView(source);
  const url = safeSourceUrl(source.source_url);
  return <>
    {view.kind === "repealed" && <div className="ctz-currency is-repealed" role="note">
      <CircleAlert size={15} aria-hidden="true"/>
      <div>
        <strong>No longer in force{view.repealedOn ? ` from ${view.repealedOn}` : ""}</strong>
        <p>{view.replacedBy ? `Replaced by ${view.replacedBy}. ` : ""}It may still apply to conduct from before that date, but not to anything happening now.</p>
      </div>
    </div>}
    {view.kind === "moved" && <div className="ctz-currency" role="note">
      <CircleAlert size={15} aria-hidden="true"/>
      <div>
        <strong>Still in force, but cites provisions that have moved</strong>
        {!!view.mappings?.length && <ul>{view.mappings.map(mapping => <li key={`${mapping.from_code}-${mapping.from_section}-${mapping.to_section}`}>
          {mapping.from_code} s.{mapping.from_section} → {mapping.to_code} s.{mapping.to_section}{mapping.subject ? ` (${mapping.subject})` : ""}
          {mapping.ingredients_changed && <em> Elements changed.</em>}
        </li>)}</ul>}
        {!!view.unmapped.length && <p>No mapping recorded for {view.unmapped.join(", ")}. Check the replacement Act directly.</p>}
        {view.pendingReview && <p>Section mappings are indicative and awaiting legal review.</p>}
      </div>
    </div>}
    {url && <a className="ctz-source-link" href={url} target="_blank" rel="noreferrer">Open the official source<ArrowUpRight size={13} aria-hidden="true"/></a>}
  </>;
}
