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
    paragraphs.shift() || "Review the source-supported findings below.";
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
