/**
 * An answer as a document someone can keep, with its citations still attached.
 *
 * A copy of the answer without its sources is exactly what this product exists
 * to prevent, so the sources travel with it, including what replaced anything
 * no longer in force. The answer text came from a language model and may quote
 * an uploaded document, so it is treated as hostile input here: everything is
 * escaped before any formatting is applied.
 */
import type { AgentCitation, ChatMessage } from "./types";

export const NOT_ADVICE =
  "Legal information, not legal advice. It does not take your full circumstances into account. Check the current official text, and speak to an advocate or a legal services authority before acting on it in a live matter.";

export interface ExportInput {
  question?: string;
  message: Pick<ChatMessage, "content" | "citations" | "evidenceStrength" | "responseMode">;
  exportedAt?: Date;
}

export function gradeLabel(message: ExportInput["message"]): string {
  if (message.responseMode === "fast") return "Relevance preview: passages found, claims not verified";
  if (message.evidenceStrength === "strong") return "High confidence in the retrieved sources";
  if (message.evidenceStrength === "moderate") return "Moderate confidence: some gaps remain";
  if (message.evidenceStrength === "insufficient") return "Limited evidence";
  return "Grade not recorded";
}

/** Only web links. `javascript:` and friends must not survive into a saved file. */
export function safeSourceUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : null;
  } catch {
    return null;
  }
}

export function citationLocation(citation: AgentCitation): string {
  const pages =
    citation.page_start === citation.page_end
      ? `page ${citation.page_start}`
      : `pages ${citation.page_start}–${citation.page_end}`;
  return [citation.section ? `Section ${citation.section}` : null, pages].filter(Boolean).join(", ");
}

/** Everything the reader must know about whether this source is still the law. */
export function citationCurrency(citation: AgentCitation): string[] {
  const notes: string[] = [];
  if (citation.repeal_label === "no_longer_in_force" || citation.current_status === "repealed") {
    notes.push(
      `No longer in force${citation.repealed_on ? ` (repealed ${citation.repealed_on})` : ""}${citation.replaced_by ? `. Replaced by ${citation.replaced_by}` : ""}.`,
    );
  } else if (citation.current_status === "superseded") {
    notes.push(`Superseded${citation.replaced_by ? ` by ${citation.replaced_by}` : ""}.`);
  } else if (citation.repeal_label === "concerns_repealed_provision") {
    notes.push("In force, but cites provisions renumbered on 1 July 2024.");
  }
  for (const mapping of citation.section_mappings ?? []) {
    notes.push(
      `${mapping.from_code} s.${mapping.from_section} is now ${mapping.to_code} s.${mapping.to_section}${mapping.ingredients_changed ? " (a different offence, not a renumbering)" : ""}.`,
    );
  }
  return notes;
}

export function answerToMarkdown(input: ExportInput): string {
  const { message, question } = input;
  const citations = message.citations ?? [];
  const lines: string[] = ["# Corpusil research note", ""];
  if (input.exportedAt) lines.push(`Exported ${input.exportedAt.toISOString().slice(0, 10)}`, "");
  if (question) lines.push("## Question", "", question.trim(), "");
  lines.push("## Answer", "", `*${gradeLabel(message)}*`, "", message.content.trim(), "");
  lines.push("## Sources", "");
  if (!citations.length) lines.push("No authority was cited.", "");
  for (const citation of citations) {
    lines.push(`**[Source ${citation.number}] ${citation.title}**`, "");
    lines.push(`- ${citationLocation(citation)}`);
    if (citation.verification_status) lines.push(`- Claim check: ${citation.verification_status}`);
    const url = safeSourceUrl(citation.source_url);
    if (url) lines.push(`- Official source: ${url}`);
    for (const note of citationCurrency(citation)) lines.push(`- ${note}`);
    lines.push("");
    for (const line of citation.excerpt.trim().split("\n")) lines.push(`> ${line}`);
    lines.push("");
  }
  lines.push("---", "", NOT_ADVICE, "");
  return lines.join("\n");
}

export function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function inlineHtml(text: string): string {
  return escapeHtml(text)
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\[Source (\d+)\]/g, '<a href="#source-$1">[Source $1]</a>');
}

/**
 * The small subset of Markdown answers use. Links are deliberately not parsed:
 * a link in model output could point anywhere, and the sources section already
 * carries every link this document should contain.
 */
export function bodyToHtml(markdown: string): string {
  const blocks: string[] = [];
  let list: string[] = [];
  let ordered = false;
  const flush = () => {
    if (!list.length) return;
    const tag = ordered ? "ol" : "ul";
    blocks.push(`<${tag}>${list.map(item => `<li>${item}</li>`).join("")}</${tag}>`);
    list = [];
  };
  for (const raw of markdown.split(/\n/)) {
    const line = raw.trim();
    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    const bullet = line.match(/^[-*]\s+(.*)$/);
    const numbered = line.match(/^\d+[.)]\s+(.*)$/);
    if (bullet || numbered) {
      const isOrdered = Boolean(numbered);
      if (list.length && ordered !== isOrdered) flush();
      ordered = isOrdered;
      list.push(inlineHtml((bullet ?? numbered)![1]));
      continue;
    }
    flush();
    if (!line) continue;
    if (heading) blocks.push(`<h3>${inlineHtml(heading[2])}</h3>`);
    else if (line.startsWith("> ")) blocks.push(`<blockquote>${inlineHtml(line.slice(2))}</blockquote>`);
    else blocks.push(`<p>${inlineHtml(line)}</p>`);
  }
  flush();
  return blocks.join("\n");
}

const STYLES = `body{max-width:46rem;margin:2.5rem auto;padding:0 1.25rem;font:16px/1.65 Georgia,'Times New Roman',serif;color:#1d1f1e;background:#fff}
h1{font-size:1.5rem;margin:0 0 .25rem}h2{font-size:1.05rem;margin:2rem 0 .5rem;border-bottom:1px solid #d5d8d4;padding-bottom:.25rem}h3{font-size:1rem;margin:1.25rem 0 .25rem}
.grade{color:#46574f;font-style:italic}blockquote{margin:.5rem 0;padding:.25rem 0 .25rem .9rem;border-left:2px solid #9aa79f;color:#333;white-space:pre-wrap}
.source{margin:1.25rem 0;break-inside:avoid}.source p{margin:.15rem 0}.currency{color:#8a3a12}.meta{font-size:.9rem;color:#46574f}.note{margin-top:2.5rem;padding-top:.75rem;border-top:1px solid #d5d8d4;font-size:.9rem}
a{color:#2f5447}@media print{a{color:inherit}body{margin:0}}`;

export function answerToHtml(input: ExportInput): string {
  const { message, question } = input;
  const citations = message.citations ?? [];
  const sources = citations.length
    ? citations
        .map(citation => {
          const url = safeSourceUrl(citation.source_url);
          return `<section class="source" id="source-${citation.number}">
<h3>[Source ${citation.number}] ${escapeHtml(citation.title)}</h3>
<p class="meta">${escapeHtml(citationLocation(citation))}${citation.verification_status ? ` · Claim check: ${escapeHtml(citation.verification_status)}` : ""}</p>
${citationCurrency(citation).map(note => `<p class="currency">${escapeHtml(note)}</p>`).join("\n")}
${url ? `<p class="meta"><a href="${escapeHtml(url)}" rel="noopener noreferrer">Official source</a></p>` : ""}
<blockquote>${escapeHtml(citation.excerpt.trim())}</blockquote>
</section>`;
        })
        .join("\n")
    : "<p>No authority was cited.</p>";
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>Corpusil research note</title>
<style>${STYLES}</style>
</head>
<body>
<h1>Corpusil research note</h1>
${input.exportedAt ? `<p class="meta">Exported ${input.exportedAt.toISOString().slice(0, 10)}</p>` : ""}
${question ? `<h2>Question</h2>\n<p>${escapeHtml(question.trim())}</p>` : ""}
<h2>Answer</h2>
<p class="grade">${escapeHtml(gradeLabel(message))}</p>
${bodyToHtml(message.content)}
<h2>Sources</h2>
${sources}
<p class="note">${escapeHtml(NOT_ADVICE)}</p>
</body>
</html>
`;
}

export function exportFilename(extension: "md" | "html", at: Date = new Date()): string {
  return `corpusil-answer-${at.toISOString().slice(0, 10)}.${extension}`;
}
