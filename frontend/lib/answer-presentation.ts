/** Restructure published text only; never infer a verdict from a question or score. */
export function presentAnswer(content: string, fast = false) {
  const normalized = content
    .replace(/^\s*\\?---\s*$/gm, "")
    .replace(/\\([*_])/g, "$1")
    .replace(/\u00a0/g, " ");
  const sections: Array<{ title: string; body: string[] }> = [{ title: "", body: [] }];
  let fenced = false;
  for (const line of normalized.split("\n")) {
    if (/^\s*```/.test(line)) fenced = !fenced;
    const heading = !fenced && line.match(/^#{1,3}\s+(.+?)\s*$/);
    if (heading) sections.push({ title: heading[1], body: [] });
    else sections[sections.length - 1].body.push(line);
  }
  const direct = sections.find(section => /^direct answer$/i.test(section.title)) ?? sections[0];
  const paragraphs = direct.body.join("\n").trim().split(/\n\s*\n/).filter(Boolean);
  const explanation = paragraphs.shift() || "Review the source-supported findings below.";
  const plain = explanation.replace(/\*\*/g, "").trim();
  const verdict = plain.match(/^(yes|no|depends|it depends)(?=[.,!:;—–]|\s*$)/i)?.[1].toLowerCase();
  const tone = verdict === "yes" ? "green" : verdict === "no" ? "maroon" : "amber";
  const headline = verdict === "yes" ? "Yes." : verdict === "no" ? "No." : verdict ? "It depends." : fast ? "Source brief." : /insufficient|not enough evidence|could not find enough reliable/i.test(plain) ? "More evidence is needed." : "What the sources establish.";
  const seen = new Set<string>();
  const dedupe = (text: string) => text.split(/\n\s*\n|\n(?=\s*[-*]\s)/).filter(block => {
    const key = block.replace(/^\s*[-*]\s/, "").replace(/\[Source \d+\]/g, "").replace(/\s+/g, " ").replace(/[.\s]+$/, "").trim().toLowerCase();
    if (!key || seen.has(key)) return false;
    seen.add(key); return true;
  }).join("\n\n");
  dedupe(explanation);
  const basis: string[] = [], other: string[] = [], limits: string[] = [], footer: string[] = [];
  if (paragraphs.length) other.push(paragraphs.join("\n\n"));
  for (const section of sections) {
    if (section === direct) continue;
    const body = section.body.join("\n").trim();
    if (!body) continue;
    if (/limit|caveat|uncertaint/i.test(section.title)) limits.push(body);
    else if (/currency|disclaimer/i.test(section.title)) footer.push(body);
    else if (/legal basis|legal position|applies to you|application to/i.test(section.title)) basis.push(dedupe(body));
    else other.push((section.title ? `### ${section.title}\n\n` : "") + body);
  }
  const body = other.join("\n\n").split(/\n\s*\n/).filter(block => {
    if (/^(?:\*\*)?(?:currency notice|disclaimer):/i.test(block.trim()) || /(?:not a substitute for|source currency|current-law status|latest official text and amendments|legal decision-support information)/i.test(block)) { footer.push(block); return false; }
    return true;
  }).join("\n\n");
  return { headline, tone, explanation, basis: basis.filter(Boolean).join("\n\n"), other: body, limits: limits.join("\n\n"), footer: footer.join("\n\n") };
}
export function legalCategory(query: string) {
  if (/police|fir\b|arrest|bail|criminal|offence|snatch|theft|crpc|bnss/i.test(query)) return "Criminal law";
  if (/marriage|divorce|custody|family/i.test(query)) return "Family law";
  if (/rent|tenant|landlord|property/i.test(query)) return "Property law";
  if (/contract|agreement/i.test(query)) return "Contract law";
  if (/constitution|article|fundamental|equality/i.test(query)) return "Constitutional law";
  return "Legal research";
}
