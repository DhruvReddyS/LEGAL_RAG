/**
 * Restructure published text for display. This function must never add
 * information the verification pipeline did not produce.
 *
 * Two rules follow from that, and both were previously broken:
 *
 * 1. No verdict is inferred from prose. Reading "Yes" off the front of a
 *    sentence and presenting it as a legal conclusion is the model's wording
 *    promoted to a finding.
 * 2. Nothing verified is deleted. The backend assembles the answer from
 *    individually verified claims, so the renderer may reorder and group but
 *    may not drop.
 */

export type PresentationOptions = {
  /** Fast mode is retrieval-only; its passages carry no verified claims. */
  fast?: boolean;
  /** Backend evidence strength. "insufficient" is the abstention signal. */
  evidenceStrength?: string | null;
};

export type Presentation = {
  headline: string;
  abstained: boolean;
  explanation: string;
  basis: string;
  other: string;
  limits: string;
  footer: string;
};

/** Stands in when an answer opens straight on a heading. */
export const NO_LEAD = "Review the source-supported findings below.";

/** Text the backend publishes when it cannot support an answer. */
const ABSTENTION_PROSE =
  /insufficient|not enough evidence|could not find enough reliable/i;

export function presentAnswer(
  content: string,
  options: PresentationOptions = {},
): Presentation {
  const { fast = false, evidenceStrength = null } = options;

  const normalized = content
    .replace(/^\s*\\?---\s*$/gm, "")
    .replace(/\\([*_])/g, "$1")
    .replace(/ /g, " ");

  const sections: Array<{ title: string; body: string[] }> = [{ title: "", body: [] }];
  let fenced = false;
  for (const line of normalized.split("\n")) {
    if (/^\s*```/.test(line)) fenced = !fenced;
    const heading = !fenced && line.match(/^#{1,3}\s+(.+?)\s*$/);
    if (heading) sections.push({ title: heading[1], body: [] });
    else sections[sections.length - 1].body.push(line);
  }

  const direct =
    sections.find(section => /^direct answer$/i.test(section.title)) ?? sections[0];
  const paragraphs = direct.body.join("\n").trim().split(/\n\s*\n/).filter(Boolean);
  const explanation =
    paragraphs.shift() || NO_LEAD;
  const plain = explanation.replace(/\*\*/g, "").trim();

  // Abstention comes from the pipeline's own evidence_strength when the caller
  // supplies it. Matching the prose was brittle: rewording the backend's
  // INSUFFICIENT_EVIDENCE constant silently downgraded an abstention to a
  // normal answer. The prose check remains only as a fallback for callers that
  // have no strength to pass.
  const abstained =
    evidenceStrength === "insufficient" ||
    (evidenceStrength === null && ABSTENTION_PROSE.test(plain));

  const headline = abstained
    ? "More evidence is needed."
    : fast
      ? "Source brief."
      : "What the sources establish.";

  // One `seen` set per section. A single set shared across sections deleted a
  // claim that legitimately appeared in more than one, after the backend had
  // verified it - the renderer silently overriding the verifier.
  const dedupe = (text: string) => {
    const seen = new Set<string>();
    return text
      .split(/\n\s*\n|\n(?=\s*[-*]\s)/)
      .filter(block => {
        const key = block
          .replace(/^\s*[-*]\s/, "")
          .replace(/\[Source \d+\]/g, "")
          .replace(/\s+/g, " ")
          .replace(/[.\s]+$/, "")
          .trim()
          .toLowerCase();
        if (!key || seen.has(key)) return false;
        seen.add(key);
        return true;
      })
      .join("\n\n");
  };

  const basis: string[] = [];
  const other: string[] = [];
  const limits: string[] = [];
  const footer: string[] = [];
  if (paragraphs.length) other.push(paragraphs.join("\n\n"));

  for (const section of sections) {
    if (section === direct) continue;
    const body = section.body.join("\n").trim();
    if (!body) continue;
    if (/limit|caveat|uncertaint/i.test(section.title)) limits.push(body);
    else if (/currency|disclaimer/i.test(section.title)) footer.push(body);
    else if (/legal basis|legal position|applies to you|application to/i.test(section.title))
      basis.push(dedupe(body));
    else other.push((section.title ? `### ${section.title}\n\n` : "") + body);
  }

  const body = other
    .join("\n\n")
    .split(/\n\s*\n/)
    .filter(block => {
      if (
        /^(?:\*\*)?(?:currency notice|disclaimer):/i.test(block.trim()) ||
        /(?:not a substitute for|source currency|current-law status|latest official text and amendments|legal decision-support information)/i.test(
          block,
        )
      ) {
        footer.push(block);
        return false;
      }
      return true;
    })
    .join("\n\n");

  return {
    headline,
    abstained,
    explanation,
    basis: basis.filter(Boolean).join("\n\n"),
    other: body,
    limits: limits.join("\n\n"),
    footer: footer.join("\n\n"),
  };
}

export function legalCategory(query: string) {
  if (/police|fir\b|arrest|bail|criminal|offence|snatch|theft|crpc|bnss/i.test(query))
    return "Criminal law";
  if (/marriage|divorce|custody|family/i.test(query)) return "Family law";
  if (/rent|tenant|landlord|property/i.test(query)) return "Property law";
  if (/contract|agreement/i.test(query)) return "Contract law";
  if (/constitution|article|fundamental|equality/i.test(query))
    return "Constitutional law";
  return "Legal research";
}

/**
 * A Fast result opens on this sentence. It describes the mode, which the source list
 * says for itself. The history row keeps no lane, so a reopened chat is recognised by it.
 */
const FAST_BRIEF_OPENING = /^\s*Fast evidence brief\b/i;

export function isFastBrief(content: string): boolean {
  return FAST_BRIEF_OPENING.test(content);
}

type SourceFields = {
  title: string;
  act_name?: string | null;
  section?: string | null;
  court?: string | null;
  current_status?: string;
  repeal_label?: string;
};

/** Act and section, as a person would name the source. */
export function sourceHeading(source: SourceFields) {
  const act = (source.act_name || source.title).trim();
  const raw = (source.section ?? "").trim().replace(/^(?:section|sec\.?|s\.)\s*/i, "");
  const key = (text: string) => text.toLowerCase().replace(/^the\s+/, "").replace(/[^a-z0-9]+/g, " ").trim();
  const sameDocument = key(source.title).includes(key(act)) || key(act).includes(key(source.title));
  return {
    act,
    section: raw || null,
    sectionIsNumber: /^\d/.test(raw),
    detail: sameDocument ? (source.court ?? null) : source.title,
  };
}

export type SourceStandingLabel = "sourceRepealed" | "currencyMoved" | "currencyCurrent" | "currencyRepealed" | "currencySuperseded" | "currencyUnknown";

/**
 * Where a source stands. "Marked current" and not "In force": the corpus records a
 * status, and later changes may not be in it.
 */
export function sourceStanding(source: SourceFields): { tone: "ok" | "warn" | "bad" | "plain"; label: SourceStandingLabel } {
  if (source.repeal_label === "no_longer_in_force") return { tone: "bad", label: "sourceRepealed" };
  if (source.repeal_label === "concerns_repealed_provision") return { tone: "warn", label: "currencyMoved" };
  if (source.current_status === "current") return { tone: "ok", label: "currencyCurrent" };
  if (source.current_status === "repealed") return { tone: "bad", label: "currencyRepealed" };
  if (source.current_status === "superseded") return { tone: "warn", label: "currencySuperseded" };
  return { tone: "plain", label: "currencyUnknown" };
}

/**
 * Which step of the wait a job's reported stage belongs to. No label yet means the
 * job has only just started; a label from outside the pipeline (a queue position)
 * is no step at all, and answers -1.
 */
export function deepStageIndex(label: string | null | undefined): number {
  if (!label) return 0;
  if (/check/i.test(label)) return 2;
  if (/writing/i.test(label)) return 3;
  if (/working through|reading|analys/i.test(label)) return 1;
  if (/search|prepar|understand/i.test(label)) return 0;
  return -1;
}
