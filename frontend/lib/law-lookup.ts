import { request } from "./api";

export interface ProvisionText {
  title: string;
  act_name: string;
  section: string;
  text: string;
  page_start: number;
  page_end: number;
  source_url: string | null;
  jurisdiction: string | null;
  currency_status: "in_force" | "superseded" | "unverified" | string;
  superseded_by: string | null;
  currency_basis: string | null;
}

export interface ProvisionCounterpart {
  from_code: string;
  from_section: string;
  to_code: string;
  to_section: string | null;
  subject: string;
  ingredients_changed: boolean;
  note: string | null;
}

export interface LawLookupResult {
  query: string;
  understood: boolean;
  act: string | null;
  section: string | null;
  provisions: ProvisionText[];
  counterparts: ProvisionCounterpart[];
}

export function lookupProvision(query: string, signal?: AbortSignal): Promise<LawLookupResult> {
  return request(`/law/lookup?q=${encodeURIComponent(query)}`, { signal });
}

/** A citation that opens a counterpart when followed. */
export function counterpartCitation(item: ProvisionCounterpart): string | null {
  return item.to_section ? `${item.to_code} ${item.to_section}` : null;
}

export const CURRENCY_LABEL: Record<string, string> = {
  in_force: "In force",
  superseded: "Replaced or repealed",
  unverified: "Currency not verified",
};
