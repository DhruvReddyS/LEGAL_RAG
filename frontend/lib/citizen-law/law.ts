/**
 * The law citizen tools may cite, and nothing else.
 *
 * provisions.json holds a verbatim quote for every provision, in the words of
 * the corpus document named beside it. backend/tests/
 * test_citizen_law_is_in_the_corpus.py reads each quote against the corpus, and
 * frontend/tests/citizen-content.test.cjs fails if content cites an id that is
 * not here. Quotes are never translated: only our explanation of them is.
 */
import data from "./provisions.json";

export type Lang = "en" | "hi" | "te";
export const LANGS: Lang[] = ["en", "hi", "te"];
export type L = Record<Lang, string>;
export const l = (en: string, hi: string, te: string): L => ({ en, hi, te });

const SHORT_ACT: Record<string, string> = {
  BNSS: "BNSS", BNS: "BNS", CONST: "Constitution", LSA: "Legal Services Authorities Act", LIM: "Limitation Act",
  CPA: "Consumer Protection Act", CPAFAQ: "Consumer Affairs FAQs", NI: "Negotiable Instruments Act", DV: "Domestic Violence Act",
  POSH: "Workplace Harassment Act", RTI: "RTI Act", RTIR: "RTI Rules 2012", IT: "IT Act", ITKIT: "IT Act", ITFORM: "IT Act",
  TPA: "Transfer of Property Act", APTEN: "AP Tenancy Act 2017", CPC: "CPC", NALSA: "NALSA", NALSACHILD: "NALSA", MHA: "MHA",
  NALSAMH: "NALSA", PORTAL: "Reporting portal",
};

export type Provision = {
  id: string;
  label: string;
  actName: string;
  quote: string;
  page: number | null;
  sourceUrl: string;
};

type Entry = { act: string; section: string; quote: string; page: number | null };
type Act = { name: string; source_url: string };

export function hasProvision(id: string): boolean {
  return id in (data.provisions as Record<string, Entry>);
}

export function provision(id: string): Provision {
  const entry = (data.provisions as Record<string, Entry>)[id];
  if (!entry) throw new Error(`Unknown provision: ${id}`);
  const act = (data.acts as Record<string, Act>)[entry.act];
  return {
    id,
    label: `${SHORT_ACT[entry.act] ?? entry.act} ${entry.section}`.trim(),
    actName: act.name,
    quote: entry.quote,
    page: entry.page ?? null,
    sourceUrl: act.source_url,
  };
}

export function provisions(ids: string[]): Provision[] {
  return ids.map(provision);
}
