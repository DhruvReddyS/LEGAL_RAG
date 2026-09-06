const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

// The components that render inside a workspace. MessageBubble is the
// reference: the citizen surface has always been token-only, which is why it
// works under both themes.
const COMPONENTS = [
  'components/MessageBubble.tsx',
  'components/ProfessionalWorkspace.tsx',
  'components/InvestigationTimeline.tsx',
  'components/ComplianceChecklist.tsx',
  'components/AuthorityCheck.tsx',
];

test('no workspace component hardcodes a colour', () => {
  // A literal renders one theme correctly and the other unreadably. The
  // police and advocate surfaces were built this way and showed cream
  // panels on a near-black page under the ink theme, with the toggle
  // sitting in settings the whole time.
  for (const file of COMPONENTS) {
    const source = fs.readFileSync(file, 'utf8');
    const literals = source.match(/#[0-9a-fA-F]{6}\b/g) || [];
    assert.deepEqual(
      literals,
      [],
      `${file} hardcodes ${literals.join(', ')}. Use a CSS variable so both themes resolve.`,
    );
  }
});

test('every status token is defined in both themes', () => {
  // A token defined only in :root renders as nothing under the ink theme,
  // which is worse than a literal: the element loses its background
  // entirely rather than merely looking wrong.
  const css = fs.readFileSync('app/globals.css', 'utf8');
  const light = css.match(/:root\s*\{[^}]*\}/g).join('');
  const ink = css.match(/:root\[data-theme="ink"\]\s*\{[^}]*\}/g).join('');

  const tokens = [...new Set((css.match(/--state-[a-z-]+/g) || []))];
  assert.ok(tokens.length >= 9, `expected the full status set, found ${tokens.length}`);

  for (const token of tokens) {
    assert.ok(light.includes(`${token}:`), `${token} is not defined for the light theme`);
    assert.ok(ink.includes(`${token}:`), `${token} is not defined for the ink theme`);
  }
});

test('the three states are visually distinct in both themes', () => {
  // Two states that resolve to the same colour collapse the distinction the
  // whole design rests on: an unknown is not a pass and not a failure.
  const css = fs.readFileSync('app/globals.css', 'utf8');
  for (const block of [
    css.match(/:root\s*\{[^}]*\}/g).join(''),
    css.match(/:root\[data-theme="ink"\]\s*\{[^}]*\}/g).join(''),
  ]) {
    const backgrounds = ['ok', 'warn', 'bad'].map(state => {
      const found = block.match(new RegExp(`--state-${state}-bg:\\s*(#[0-9a-fA-F]{6})`));
      assert.ok(found, `--state-${state}-bg missing`);
      return found[1].toLowerCase();
    });
    assert.equal(new Set(backgrounds).size, 3, `states collapse: ${backgrounds.join(', ')}`);
  }
});
