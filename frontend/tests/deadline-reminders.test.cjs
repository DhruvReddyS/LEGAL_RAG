const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const loadTs = require('./load-ts.cjs');
const lib = loadTs('lib/deadline-reminders.ts', { String, Array, Object });
const { reminderPermission, dueCitizenIds, dueAdvocateIds, duePoliceIds, localDay, remindOfNewItems, SEEN_STORAGE_KEY } = lib;

const plain = value => [...value];
const memory = (initial = {}) => {
  const values = { ...initial };
  return { values, getItem: key => values[key] ?? null, setItem: (key, value) => { values[key] = value; } };
};

test('a page without Notification support reports it, and nothing else is asked of it', () => {
  assert.equal(reminderPermission(undefined), 'unsupported');
  assert.equal(reminderPermission({}), 'unsupported');
  assert.equal(reminderPermission({ Notification: { permission: 'granted' } }), 'granted');
  assert.equal(reminderPermission({ Notification: { permission: 'denied' } }), 'denied');
  assert.equal(reminderPermission({ Notification: { permission: 'default' } }), 'default');
});

test('only overdue and due-today items count, for a citizen and an advocate', () => {
  assert.deepEqual(plain(dueCitizenIds([
    { id: 'a', status: 'overdue', completed_at: null },
    { id: 'b', status: 'due_today', completed_at: null },
    { id: 'c', status: 'due_soon', completed_at: null },
    { id: 'd', status: 'overdue', completed_at: '2026-11-01' },
  ])), ['citizen:a', 'citizen:b']);
  assert.deepEqual(plain(dueAdvocateIds([
    { id: 'a', state: 'overdue', completed: false },
    { id: 'b', state: 'due_today', completed: false },
    { id: 'c', state: 'due_soon', completed: false },
    { id: 'd', state: 'overdue', completed: true },
  ])), ['advocate:a', 'advocate:b']);
});

test('the police register counts breached, overdue, and due on this day only', () => {
  const today = localDay(new Date(2026, 10, 5, 9));
  const row = (key, state, due_at, completed_at = null) => ({ case_id: 'c', key, state, due_at, completed_at });
  assert.deepEqual(plain(duePoliceIds([
    row('breached', 'breached', null),
    row('overdue', 'overdue', null),
    row('today', 'due', new Date(2026, 10, 5, 20).toISOString()),
    row('later', 'due', new Date(2026, 10, 6, 20).toISOString()),
    row('unknown', 'unknown', null),
    row('no-date', 'due', null),
    row('done', 'overdue', null, '2026-11-01'),
  ], today)), ['police:c:breached', 'police:c:overdue', 'police:c:today']);
});

test('an item reminds once a day, and a new item reminds on its own', () => {
  const store = memory();
  const counts = [];
  const check = (dueIds, today) => remindOfNewItems({ dueIds, today, store, notify: count => counts.push(count) });
  assert.equal(check(['a', 'b'], '2026-11-05'), 2);
  assert.equal(check(['a', 'b'], '2026-11-05'), 0);
  assert.equal(check(['a', 'b', 'c'], '2026-11-05'), 1);
  assert.equal(check(['a', 'b', 'c'], '2026-11-06'), 3, 'the next day they count again');
  assert.deepEqual(counts, [2, 1, 3]);
});

test('storage that throws or holds rubbish does not stop the reminder', () => {
  const counts = [];
  const notify = count => counts.push(count);
  const broken = { getItem() { throw new Error('denied'); }, setItem() { throw new Error('denied'); } };
  assert.equal(remindOfNewItems({ dueIds: ['a'], today: 'd', store: broken, notify }), 1);
  assert.equal(remindOfNewItems({ dueIds: ['a'], today: 'd', store: null, notify }), 1);
  const rubbish = memory({ [SEEN_STORAGE_KEY]: '{not json' });
  assert.equal(remindOfNewItems({ dueIds: ['a'], today: 'd', store: rubbish, notify }), 1);
  assert.deepEqual(counts, [1, 1, 1]);
});

test('a notification that fails is not marked as seen', () => {
  const store = memory();
  const failing = remindOfNewItems({ dueIds: ['a'], today: 'd', store, notify: () => { throw new Error('no constructor here'); } });
  assert.equal(failing, 0);
  assert.equal(store.values[SEEN_STORAGE_KEY], undefined);
  assert.equal(remindOfNewItems({ dueIds: ['a'], today: 'd', store, notify: () => {} }), 1);
});

test('nothing due makes no notification', () => {
  let called = false;
  assert.equal(remindOfNewItems({ dueIds: [], today: 'd', store: memory(), notify: () => { called = true; } }), 0);
  assert.equal(called, false);
});

test('what a lock screen shows is a count, in every language', () => {
  const { UI } = loadTs('lib/citizen-i18n.ts', { require: () => ({ l: (en, hi, te) => ({ en, hi, te }), LANGS: ['en', 'hi', 'te'] }), Object });
  for (const lang of ['en', 'hi', 'te']) {
    assert.ok(UI.reminderOne[lang]);
    assert.match(UI.reminderMany[lang], /\{n\}/);
  }
  const source = fs.readFileSync('components/platform/DeadlineReminders.tsx', 'utf8');
  const made = source.match(/new Notification\(([^)]*)\)/)[1];
  assert.equal(made, '"Corpusil", { body, tag: REMINDER_TAG }');
  assert.doesNotMatch(source, /\.title|case_title|obligation|\.notes/);
});

test('permission is asked for only from a button in Settings', () => {
  const source = fs.readFileSync('components/platform/DeadlineReminders.tsx', 'utf8');
  assert.equal((source.match(/requestPermission/g) || []).length, 1);
  assert.match(source, /const ask = async \(\) =>[\s\S]*requestPermission[\s\S]*onClick=\{\(\) => void ask\(\)\}/);
});
