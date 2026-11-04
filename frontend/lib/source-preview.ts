/**
 * F11: what the chat source preview says about a source's currency. The legal
 * note tells a reader to open this panel to see what replaced a source, so the
 * panel has to carry it.
 */
import type { AgentCitation } from "./types";

export type CurrencyView =
  | { kind: "repealed"; repealedOn: string | null; replacedBy: string | null }
  | { kind: "moved"; mappings: AgentCitation["section_mappings"]; unmapped: string[]; pendingReview: boolean }
  | { kind: "none" };

export function currencyView(source: Pick<AgentCitation, "repeal_label" | "repealed_on" | "replaced_by" | "section_mappings" | "unmapped_repealed_provisions" | "mapping_review_status">): CurrencyView {
  if (source.repeal_label === "no_longer_in_force") {
    return { kind: "repealed", repealedOn: source.repealed_on ?? null, replacedBy: source.replaced_by ?? null };
  }
  if (source.repeal_label === "concerns_repealed_provision") {
    return {
      kind: "moved",
      mappings: source.section_mappings ?? [],
      unmapped: source.unmapped_repealed_provisions ?? [],
      pendingReview: source.mapping_review_status === "pending_legal_review",
    };
  }
  return { kind: "none" };
}

/** A source link comes from data, so only a real web address becomes a link. */
export function safeSourceUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : null;
  } catch {
    return null;
  }
}
