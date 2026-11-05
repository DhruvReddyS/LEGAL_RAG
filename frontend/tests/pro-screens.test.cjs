const test = require('node:test');
const assert = require('node:assert/strict');
const loadTs = require('./load-ts.cjs');

const route = loadTs('lib/pro-route.ts', { URLSearchParams });
const screens = loadTs('lib/pro-presentation.ts');

const ID = '00000000-0000-4000-8000-000000000004';
const plain = (value) => JSON.parse(JSON.stringify(value));

test('an address reads back as the screen it was written from', () => {
  for (const to of [
    { section: 'dashboard' },
    { section: 'cases' },
    { section: 'case', caseId: ID },
    { section: 'case', caseId: ID, tab: 'files' },
    { section: 'case', caseId: ID, tab: 'files', tool: 'witnesses' },
    { section: 'deadlines' },
    { section: 'research' },
    { section: 'research', chat: ID },
    { section: 'case', caseId: ID, tab: 'ask', chat: ID },
    { section: 'law' },
  ]) {
    assert.deepEqual(plain(route.parseProRoute(route.proHref(to).slice(1))), to);
  }
});

test('an address that means nothing lands somewhere safe, never on a broken screen', () => {
  assert.deepEqual(plain(route.parseProRoute('')), { section: 'dashboard' });
  assert.deepEqual(plain(route.parseProRoute('?signin')), { section: 'dashboard' });
  assert.deepEqual(plain(route.parseProRoute('?s=nonsense')), { section: 'dashboard' });
  assert.deepEqual(plain(route.parseProRoute('?s=case')), { section: 'cases' });
  assert.deepEqual(plain(route.parseProRoute('?s=case&case=../../admin')), { section: 'cases' });
  assert.deepEqual(plain(route.parseProRoute(`?s=case&case=${ID}&tab=%3Cscript%3E`)), { section: 'case', caseId: ID });
});

test('today is the reader\'s own date, not the UTC one', () => {
  const { localDay } = loadTs('lib/local-day.ts');
  // 00:30 local on 5 Nov, in any zone. toISOString would say the 4th east of Greenwich.
  assert.equal(localDay(new Date(2026, 10, 5, 0, 30)), '2026-11-05');
  assert.equal(localDay(new Date(2026, 0, 9, 23, 59)), '2026-01-09');
});

test('an open conversation is held in the address only on a screen that shows one', () => {
  assert.deepEqual(plain(route.parseProRoute(`?s=case&case=${ID}&tab=files&chat=${ID}`)), { section: 'case', caseId: ID, tab: 'files' });
  assert.deepEqual(plain(route.parseProRoute(`?s=case&case=${ID}&tab=ask&chat=../../etc`)), { section: 'case', caseId: ID, tab: 'ask' });
  assert.deepEqual(plain(route.parseProRoute(`?s=research&chat=nope`)), { section: 'research' });
  assert.deepEqual(plain(route.parseProRoute(`?s=cases&chat=${ID}`)), { section: 'cases' });
});

test('a tool without a tab is dropped, and the law lookup keeps its own query', () => {
  assert.deepEqual(plain(route.parseProRoute(`?s=case&case=${ID}&tool=bail`)), { section: 'case', caseId: ID });
  assert.deepEqual(plain(route.parseProRoute('?q=BNSS%20173')), { section: 'law' });
});

const due = (id, bucket, at, caseId = 'a') => ({ id, caseId, caseTitle: caseId, title: id, when: '', relative: '', at, status: '', tone: 'neutral', bucket, tag: '' });

test('what is missed or running out comes first, and earliest within that', () => {
  const sorted = screens.sortDue([due('later', 'upcoming', 5), due('over', 'act_now', 9), due('none', 'unknown', null), due('soon', 'soon', 2), due('over-first', 'act_now', 1)]);
  assert.deepEqual(plain(sorted.map((item) => item.id)), ['over-first', 'over', 'soon', 'later', 'none']);
});

test('the dashboard asks for attention only where something can be done or was missed', () => {
  const items = [due('a', 'act_now', 1), due('b', 'breached', 1), due('c', 'soon', 1), due('d', 'upcoming', 1), due('e', 'others', 1), due('f', 'unknown', null), due('g', 'done', 1)];
  assert.deepEqual(plain(screens.needsAttention(items).map((item) => item.id)), ['a', 'b', 'c']);
});

test('the next item in a case is never finished, already missed, or someone else\'s', () => {
  const next = screens.nextDueByCase([due('done', 'done', 1), due('other', 'others', 1), due('missed', 'breached', 1), due('real', 'upcoming', 9), due('sooner', 'soon', 3), due('elsewhere', 'upcoming', 1, 'b')]);
  assert.equal(next.get('a').id, 'sooner');
  assert.equal(next.get('b').id, 'elsewhere');
  assert.equal(screens.nextDueByCase([due('done', 'done', 1)]).size, 0);
});

const CASES = [
  { id: '00000000-0000-4000-8000-0000000000aa', title: 'Beta', status: 'open', created_at: '2026-01-01T00:00:00Z' },
  { id: '00000000-0000-4000-8000-0000000000bb', title: 'Alpha', status: 'open', created_at: '2026-03-01T00:00:00Z' },
  { id: '00000000-0000-4000-8000-0000000000cc', title: 'Gamma', status: 'closed', created_at: '2026-02-01T00:00:00Z' },
];
const list = (options) => screens.visibleCases(CASES, { query: '', status: 'all', sort: 'title', next: new Map(), activity: new Map(), ...options }).map((item) => item.title);

test('cases filter by status and search by title or reference', () => {
  assert.deepEqual(list({ status: 'open' }), ['Alpha', 'Beta']);
  assert.deepEqual(list({ status: 'closed' }), ['Gamma']);
  assert.deepEqual(list({ query: 'alp' }), ['Alpha']);
  assert.deepEqual(list({ query: screens.caseReference(CASES[2].id) }), ['Gamma']);
  assert.deepEqual(list({ query: 'nothing like it' }), []);
});

test('cases sort by each thing the list offers', () => {
  assert.deepEqual(list({ sort: 'newest' }), ['Alpha', 'Gamma', 'Beta']);
  const activity = new Map([[CASES[0].id, Date.parse('2026-06-01T00:00:00Z')]]);
  assert.deepEqual(list({ sort: 'activity', activity }), ['Beta', 'Alpha', 'Gamma']);
  const next = new Map([[CASES[2].id, due('x', 'act_now', 1)], [CASES[0].id, due('y', 'upcoming', 1)]]);
  assert.deepEqual(list({ sort: 'urgent', next }), ['Gamma', 'Beta', 'Alpha']);
});

test('a date that cannot be read says so rather than inventing one', () => {
  assert.equal(screens.shortDate(null), '—');
  assert.equal(screens.shortDate(0), '—');
  assert.equal(screens.shortDate('not a date'), '—');
  assert.equal(screens.plural(1, 'file'), '1 file');
  assert.equal(screens.plural(2, 'file'), '2 files');
});
