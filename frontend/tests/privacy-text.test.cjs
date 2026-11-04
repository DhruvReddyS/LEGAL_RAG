const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const loadTs = require('./load-ts.cjs');

const text = loadTs('lib/privacy-text.ts');
const backend = fs.readFileSync('../backend/app/services/privacy_notice.py', 'utf8');
const unify = value => value.replace(/\s+/g, ' ');
const backendFlat = unify(backend);

test('the page and the backend are on the same notice version', () => {
  assert.ok(backend.includes(`PRIVACY_NOTICE_VERSION = "${text.PRIVACY_NOTICE_VERSION}"`));
});

test('every line of the page is word for word what consent is recorded against', () => {
  const lines = [
    ...text.PERSONAL_DATA_ITEMS.flat(),
    ...text.PURPOSES,
    ...text.WHAT_DOES_NOT_HAPPEN,
    ...text.KNOWN_EXCEPTIONS,
  ];
  for (const line of lines) assert.ok(backendFlat.includes(unify(line)), line);
});

test('nothing in the backend notice is missing from the page', () => {
  const count = pattern => (backend.match(pattern) || []).length;
  assert.equal(text.PERSONAL_DATA_ITEMS.length + text.PURPOSES.length + text.WHAT_DOES_NOT_HAPPEN.length + text.KNOWN_EXCEPTIONS.length,
    count(/^\s+\("[^"]+", "/gm) + count(/^\s+"[A-Z][^"]+\.",$/gm));
});

const privacyPage = fs.readFileSync('app/privacy/page.tsx', 'utf8');

test('the page says the operative law has not commenced rather than implying it binds today', () => {
  assert.match(privacyPage, /eighteen months/);
  assert.match(privacyPage, /G\.S\.R\. 843\(E\)/);
});

test('the page cites only what was read in the corpus', () => {
  // The Act's own text is not in the corpus. The Rules and the commencement
  // notification are, so section numbers of the Act may appear only as the
  // commencement notification states them.
  assert.doesNotMatch(privacyPage, /section (11|12|13|14)\b/i);
  assert.match(privacyPage, /Rules, 2025/);
});
