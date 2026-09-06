const test = require('node:test');
const assert = require('node:assert/strict');

// The status cycle, mirrored from components/ComplianceChecklist.tsx. The
// component is not testable in this project's setup; the ordering is the
// part that carries meaning, so it is asserted here.
const CYCLE = { not_recorded: 'satisfied', satisfied: 'not_satisfied', not_satisfied: 'not_recorded' };

test('the cycle passes through all three states and returns', () => {
  // A checkbox has two. Collapsing "nobody recorded this" into "not done"
  // makes a complete investigation look unlawful; collapsing it into "done"
  // certifies one nobody checked.
  let state = 'not_recorded';
  const seen = [state];
  for (let i = 0; i < 3; i += 1) { state = CYCLE[state]; seen.push(state); }
  assert.deepEqual(seen, ['not_recorded', 'satisfied', 'not_satisfied', 'not_recorded']);
});

test('every state is reachable, so a mistaken tick can be withdrawn', () => {
  assert.equal(new Set(Object.values(CYCLE)).size, 3);
  assert.ok(Object.values(CYCLE).includes('not_recorded'));
});

// What the component sends: only confirmed states. Omitting a key is what
// returns it to not_recorded on the server.
function payload(items) {
  const out = {};
  for (const item of items) if (item.status !== 'not_recorded') out[item.key] = item.status;
  return out;
}

test('unrecorded items are omitted rather than sent as a status', () => {
  const sent = payload([
    { key: 'a', status: 'satisfied' },
    { key: 'b', status: 'not_recorded' },
    { key: 'c', status: 'not_satisfied' },
  ]);
  assert.deepEqual(Object.keys(sent).sort(), ['a', 'c']);
  assert.equal('b' in sent, false);
});

test('clearing the last confirmation sends an empty map, not a stale one', () => {
  // The PUT replaces, so an empty map is how everything returns to
  // not_recorded. Sending nothing at all would leave the old record standing.
  assert.deepEqual(payload([{ key: 'a', status: 'not_recorded' }]), {});
});
