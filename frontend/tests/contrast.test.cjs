// WCAG contrast, computed from the actual tokens in the stylesheets, in both
// themes. A colour that reads fine in light mode is routinely unreadable in dark.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

// Print forces its own colours onto the same selectors, so it is not part of a theme.
const css = (fs.readFileSync('app/globals.css', 'utf8') + fs.readFileSync('app/platform.css', 'utf8')).split('@media print')[0];

function tokens(selector) {
  const found = {};
  const escaped = selector.replace(/[[\]"=:]/g, '\\$&');
  for (const match of css.matchAll(new RegExp(`${escaped}\\s*\\{([^}]*)\\}`, 'g'))) {
    for (const pair of match[1].matchAll(/(--[\w-]+)\s*:\s*(#[0-9a-fA-F]{3,6})\b/g)) found[pair[1]] = pair[2];
  }
  return found;
}

function luminance(hex) {
  const value = hex.length === 4 ? hex.slice(1).split('').map(c => c + c).join('') : hex.slice(1);
  const channel = index => {
    const v = parseInt(value.slice(index, index + 2), 16) / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(0) + 0.7152 * channel(2) + 0.0722 * channel(4);
}

function ratio(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const light = tokens(':root');
const dark = { ...light, ...tokens(':root[data-theme="ink"]') };

const TEXT_ON_SURFACE = [
  ['--ink', '--paper'],
  ['--ink', '--card'],
  ['--ink', '--sidebar'],
  ['--ink', '--hover'],
  ['--ink-soft', '--paper'],
  ['--ink-soft', '--card'],
  ['--ink-soft', '--sidebar'],
  ['--accent', '--paper'],
  ['--accent', '--card'],
  ['--accent', '--accent-soft'],
  ['--state-ok-text', '--state-ok-bg'],
  ['--state-warn-text', '--state-warn-bg'],
  ['--state-bad-text', '--state-bad-bg'],
  ['--danger-text', '--card'],
  ['--danger-text', '--paper'],
];

for (const [name, theme] of [['light', light], ['dark', dark]]) {
  for (const [text, surface] of TEXT_ON_SURFACE) {
    test(`${name}: ${text} on ${surface} meets AA for body text`, () => {
      assert.ok(theme[text], `${text} undefined`);
      assert.ok(theme[surface], `${surface} undefined`);
      const value = ratio(theme[text], theme[surface]);
      assert.ok(value >= 4.5, `${text} on ${surface} is ${value.toFixed(2)}:1`);
    });
  }
}

test('the cover colours used in both themes meet AA', () => {
  assert.ok(ratio('#f2f6f4', '#1b2621') >= 4.5);
  assert.ok(ratio('#a8bbb1', '#1b2621') >= 4.5);
});

test('reduced motion turns animation off everywhere', () => {
  assert.match(css, /prefers-reduced-motion:\s*reduce[^{]*\{[^}]*animation:none!important/);
});

test('focus stays visible', () => {
  assert.match(css, /:focus-visible\s*\{outline:2px solid var\(--accent\)/);
  assert.doesNotMatch(css, /:focus-visible\s*\{[^}]*outline:\s*(none|0)/);
});
