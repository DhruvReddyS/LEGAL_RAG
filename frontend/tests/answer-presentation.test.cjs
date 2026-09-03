const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');
const moduleScope = { exports: {} };
vm.runInNewContext(ts.transpileModule(fs.readFileSync('lib/answer-presentation.ts', 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText, moduleScope);
const { presentAnswer, legalCategory } = moduleScope.exports;

test('only explicit verdicts are elevated', () => {
  assert.equal(presentAnswer('## Direct answer\n\nYes, subject to the stated conditions.').headline, 'Yes.');
  assert.equal(presentAnswer('## Direct answer\n\nNo. This is not established.').headline, 'No.');
  assert.equal(presentAnswer('## Direct answer\n\nIt depends: facts are missing.').headline, 'It depends.');
  assert.equal(presentAnswer('No person shall be deprived of liberty.').headline, 'What the sources establish.');
  assert.equal(presentAnswer('I could not find enough reliable support in the indexed legal corpus for this answer.').headline, 'More evidence is needed.');
});
test('merge repeated legal basis while retaining distinct conditions and limits', () => {
  const result = presentAnswer('## Direct answer\n\nYes, conditionally. [Source 1]\n\n## Why this is the legal position\n\n- Preserve the notice. [Source 1]\n\n## How this applies to you\n\n- Preserve the notice. [Source 1]\n- A second condition applies. [Source 2]\n\n## Important limits\n\nConfirm commencement.');
  assert.equal((result.basis.match(/Preserve/g) || []).length, 1);
  assert.match(result.basis, /second condition/);
  assert.match(result.limits, /Confirm commencement/);
  assert.doesNotMatch(result.other, /Important limits/);
});
test('currency note moves to footer without changing source text', () => {
  const result = presentAnswer('A source preview.\n\n1. Exact quoted passage.\n\nCurrency notice: confirm current status.', true);
  assert.equal(result.headline, 'Source brief.');
  assert.match(result.footer, /Currency notice/);
  assert.doesNotMatch(result.other, /Currency notice/);
  assert.match(result.other, /Exact quoted passage/);
  assert.equal(legalCategory('FIR procedure'), 'Criminal law');
});
test('escaped and repeated legal notices do not leak into the answer body', () => {
  const result = presentAnswer('The supported answer.\n\n\\---\n\n\\*Legal decision-support information, not a substitute for advice from a qualified professional.\\*\n\nSource currency is not independently guaranteed; confirm the law in force.');
  assert.equal(result.explanation, 'The supported answer.');
  assert.doesNotMatch(result.other, /substitute|Source currency|\\---/i);
  assert.match(result.footer, /substitute|Source currency/i);
});
test('neutral light and dark theme text combinations meet AA', () => {
  const rgb = hex => hex.replace('#', '').match(/../g).map(value => parseInt(value, 16));
  const lum = color => color.map(value => { value /= 255; return value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4; }).reduce((sum, value, i) => sum + value * [.2126, .7152, .0722][i], 0);
  const ratio = (a, b) => (Math.max(lum(a), lum(b)) + .05) / (Math.min(lum(a), lum(b)) + .05);
  const css = fs.readFileSync('app/globals.css', 'utf8');
  for (const pattern of [/^:root \{([^}]+)\}/m, /^:root\[data-theme="ink"\] \{([^}]+)\}/m]) {
    const tokens = css.match(pattern)[1];
    const token = name => tokens.match(new RegExp(`--${name}:(#[a-fA-F0-9]{6})`))[1];
    for (const foreground of ['ink','ink-soft','accent']) for (const background of ['paper','card','hover']) {
      const contrast = ratio(rgb(token(foreground)), rgb(token(background)));
      assert.ok(contrast >= 4.5, `${foreground} / ${background}: ${contrast}`);
    }
  }
});
