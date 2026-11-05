const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const loadTs = require('./load-ts.cjs');
const { arrangeComparison } = loadTs('lib/law-compare.ts');

test('the earlier code is on the first side from either direction', () => {
  assert.equal(arrangeComparison('IPC', 'ipc', 'bns').earlier, 'ipc');
  assert.equal(arrangeComparison('IPC', 'ipc', 'bns').later, 'bns');
  assert.equal(arrangeComparison('BNS', 'bns', 'ipc').earlier, 'ipc');
  assert.equal(arrangeComparison('BNS', 'bns', 'ipc').later, 'bns');
  assert.equal(arrangeComparison('BNSS', 'bnss', 'crpc').earlier, 'crpc');
  assert.equal(arrangeComparison('BSA', 'bsa', 'iea').earlier, 'iea');
});

test('the comparison keeps the existing warning, and computes no diff', () => {
  const source = fs.readFileSync('components/LawLookup.tsx', 'utf8');
  assert.ok(source.includes('Wording or ingredients changed. Read both.'));
  assert.ok(!/diff/i.test(source));
});

test('the sides stack on a phone', () => {
  const css = fs.readFileSync('app/law/law.css', 'utf8');
  assert.match(css, /\.law-compare-sides \{[^}]*grid-template-columns: 1fr;/);
  assert.match(css, /@media \(min-width: 900px\) \{[^}]*\.law-compare-sides \{[^}]*repeat\(2/);
});
