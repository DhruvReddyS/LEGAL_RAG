const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');
const moduleScope = { exports: {} };
vm.runInNewContext(
  ts.transpileModule(fs.readFileSync('lib/investigation-presentation.ts', 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText,
  moduleScope,
);
const { deadlineState, assertsCompliance, summarise } = moduleScope.exports;

test('a deadline that could not be computed is neither met nor missed', () => {
  // The API returns null, never false, for these. A UI that treats null as
  // falsy collapses three states into two and reports compliance that was
  // never established -- which for the s.187(3) period means telling an
  // officer nothing is due when a default-bail entitlement may have accrued.
  const undetermined = { due_at: null, is_breached: null };

  assert.equal(deadlineState(undetermined), 'undetermined');
  assert.equal(assertsCompliance(undetermined), false);
});

test('a null is_breached is undetermined even if a due date somehow arrived', () => {
  // Defence in depth against a partially populated row: either field being
  // absent means nobody made a finding.
  assert.equal(deadlineState({ due_at: '2026-01-01T00:00:00Z', is_breached: null }), 'undetermined');
});

test('an overdue deadline reads as overdue', () => {
  const overdue = { due_at: '2020-01-01T00:00:00Z', is_breached: true };

  assert.equal(deadlineState(overdue), 'overdue');
  assert.equal(assertsCompliance(overdue), false);
});

test('only a computed, unbreached deadline asserts compliance', () => {
  const pending = { due_at: '2099-01-01T00:00:00Z', is_breached: false };

  assert.equal(deadlineState(pending), 'pending');
  assert.equal(assertsCompliance(pending), true);
});

test('the badge counts come from the rows, so they cannot disagree with them', () => {
  // Counting from the API's summary arrays instead would let the badges say
  // "0 cannot be determined" above a row that says exactly that.
  const counts = summarise([
    { due_at: null, is_breached: null },
    { due_at: '2020-01-01T00:00:00Z', is_breached: true },
    { due_at: '2099-01-01T00:00:00Z', is_breached: false },
    { due_at: null, is_breached: null },
  ]);

  // Field by field: the module is evaluated in a vm realm, so its objects
  // carry a different Object prototype and deepStrictEqual fails on identity
  // even when every value matches.
  assert.equal(counts.tracked, 4);
  assert.equal(counts.overdue, 1);
  assert.equal(counts.undetermined, 2);
});
