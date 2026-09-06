const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

// Every component, not a chosen few. The first version of this file listed
// five, which is how 290 hardcoded colours in the other seven went on
// rendering a white card on a near-black page under the ink theme.
const COMPONENT_DIR = 'components';
const COMPONENTS = fs
  .readdirSync(COMPONENT_DIR)
  .filter(name => name.endsWith('.tsx'))
  .map(name => path.join(COMPONENT_DIR, name))
  .concat(['app/page.tsx']);

// Colours that are deliberately fixed, with the reason. A scrim is a wash
// over whatever is behind it and does not follow the theme; the desktop
// dialog's header band is branded dark in both themes, like the auth screen.
// Anything not listed here has to be a token.
const DELIBERATE = {
  '#10201d': 'modal scrim, and the desktop dialog’s dark header band',
  '#07111f': 'modal scrim on the desktop readiness dialog',
};
const DELIBERATE_UTILITIES = /\b(?:border|text)-white\b/;

test('no component hardcodes a colour outside the documented exceptions', () => {
  for (const file of COMPONENTS) {
    const source = fs.readFileSync(file, 'utf8');
    const unexpected = (source.match(/#[0-9a-fA-F]{6}\b/g) || [])
      .map(value => value.toLowerCase())
      .filter(value => !(value in DELIBERATE));
    assert.deepEqual(
      unexpected,
      [],
      `${file} hardcodes ${[...new Set(unexpected)].join(', ')}. Use a CSS variable, ` +
        'or add it to DELIBERATE with the reason it must not follow the theme.',
    );
  }
});

test('no component paints a bare white surface', () => {
  // bg-white is a literal by another name: a white card on a near-black
  // page. text-white and border-white survive only where they sit on a
  // deliberately dark surface.
  for (const file of COMPONENTS) {
    const source = fs.readFileSync(file, 'utf8').replace(DELIBERATE_UTILITIES, '');
    assert.equal(
      /\bbg-white\b/.test(source),
      false,
      `${file} paints bg-white. Use bg-[var(--card)] so the ink theme resolves.`,
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
