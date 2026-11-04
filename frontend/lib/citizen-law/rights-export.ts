/**
 * "Save a copy" for C-04: one self-contained HTML file with no scripts and no
 * network requests, so it opens from a phone's files with no signal at all.
 * Quotes stay in English. Everything inserted is escaped.
 */
import { provision, type Lang } from "./law";
import { HELP_NUMBERS, RIGHTS_TOPICS } from "./rights";
import { UI } from "../citizen-i18n";

function escapeHtml(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

export function buildRightsHtml(lang: Lang): string {
  const topics = RIGHTS_TOPICS.map(topic => `<section><h2>${escapeHtml(topic.title[lang])}</h2><p class="intro">${escapeHtml(topic.intro[lang])}</p><ul>${topic.points.map(point => `<li>${escapeHtml(point.text[lang])}<small lang="en">${point.cites.map(id => {
    const cite = provision(id);
    return `${escapeHtml(cite.label)}: “${escapeHtml(cite.quote)}”`;
  }).join("<br>")}</small></li>`).join("")}</ul></section>`).join("");
  const numbers = HELP_NUMBERS.map(item => `<li><a href="tel:${item.number}">${item.number}</a> ${escapeHtml(item.label[lang])}</li>`).join("");
  return `<!doctype html>
<html lang="${lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${escapeHtml(UI.rightsPublicTitle[lang])}</title>
<style>
:root{color-scheme:light dark}
body{font:16px/1.6 system-ui,-apple-system,"Noto Sans","Noto Sans Devanagari","Noto Sans Telugu",sans-serif;max-width:720px;margin:0 auto;padding:16px}
h1{font-size:24px;line-height:1.25}h2{font-size:19px;margin-top:28px}
ul{padding-left:20px}li{margin:12px 0}small{display:block;margin-top:4px;font-size:12px;line-height:1.5;opacity:.75}
.numbers{list-style:none;padding:12px 16px;border:1px solid currentColor;border-radius:10px}.numbers li{margin:6px 0}.numbers a{font-weight:700}
.intro{opacity:.85}.note{font-size:13px;opacity:.8}
</style></head><body>
<h1>${escapeHtml(UI.rightsPublicTitle[lang])}</h1>
<h2>${escapeHtml(UI.numbersTitle[lang])}</h2><ul class="numbers">${numbers}</ul>
${topics}
<p class="note">${escapeHtml(UI.rightsLastChecked[lang])} ${escapeHtml(UI.informationNotAdvice[lang])}</p>
</body></html>
`;
}
