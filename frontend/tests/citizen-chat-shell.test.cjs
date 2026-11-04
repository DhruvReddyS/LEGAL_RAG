const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { loadTs, createLoader, ROOT } = require('./helpers/load-ts.cjs');

const chat = loadTs('lib/citizen-chat.ts');
const { currencyView, safeSourceUrl } = loadTs('lib/source-preview.ts');
const { buildIcs, dueLabel, needsAttention } = loadTs('lib/citizen-matter.ts');
const { assetsToCache } = loadTs('lib/citizen-offline.ts');

const user = (content = 'Is this legal?') => ({ id: 'u', role: 'user', content, timestamp: 1 });
const answer = (extra = {}) => ({ id: 'a', role: 'assistant', content: 'Yes', timestamp: 2, ...extra });

// F17 ------------------------------------------------------------------------

test('a loading placeholder or a failed load never reaches the sidebar', () => {
  const row = { id: 'c1', sessionId: 's1', title: 'Original title', messages: [], updatedAt: 100, messageCount: 2 };
  for (const messages of [[answer({ loading: true, content: '' })], [answer({ error: 'could not load', content: '' })]]) {
    const next = chat.syncHistoryRow([row], { activeChatId: 'c1', sessionId: 's1', messages, caseId: null }, 999);
    assert.deepEqual(next, [row]);
  }
});

test('opening a chat does not move it up or change its time', () => {
  const older = { id: 'c0', sessionId: 's0', title: 'newest', messages: [], updatedAt: 500, messageCount: 2 };
  const row = { id: 'c1', sessionId: 's1', title: 'Original title', messages: [], updatedAt: 100, messageCount: 2 };
  const next = chat.syncHistoryRow([older, row], { activeChatId: 'c1', sessionId: 's1', messages: [user(), answer()], caseId: null }, 999);
  assert.deepEqual(next.map(item => item.id), ['c0', 'c1']);
  assert.equal(next[1].updatedAt, 100);
  assert.equal(next[1].title, 'Original title');
  assert.equal(next[1].messages.length, 2, 'the body is kept for next time');
});

test('a chat that grew moves to the top', () => {
  const older = { id: 'c0', sessionId: 's0', title: 'x', messages: [], updatedAt: 500, messageCount: 2 };
  const row = { id: 'c1', sessionId: 's1', title: 'y', messages: [], updatedAt: 100, messageCount: 2, customTitle: true };
  const next = chat.syncHistoryRow([older, row], { activeChatId: 'c1', sessionId: 's1', messages: [user(), answer(), user('again'), answer()], caseId: null }, 999);
  assert.deepEqual(next.map(item => item.id), ['c1', 'c0']);
  assert.equal(next[0].updatedAt, 999);
  assert.equal(next[0].title, 'y', 'a chosen title is kept');
});

test('a brand new chat gets a row titled from its question', () => {
  const next = chat.syncHistoryRow([], { activeChatId: 'n', sessionId: 's', messages: [user('What is an FIR?'), answer()], caseId: null }, 5);
  assert.equal(next[0].title, 'What is an FIR?');
});

// F24 ------------------------------------------------------------------------

test('a later page adds only what is new', () => {
  const merged = chat.mergeHistoryPage([{ id: 'a' }, { id: 'b' }], [{ id: 'b' }, { id: 'c' }]);
  assert.deepEqual(merged.map(item => item.id), ['a', 'b', 'c']);
});

// F19 ------------------------------------------------------------------------

test('a dropped connection or a busy server is retried, a refusal is final', () => {
  assert.equal(chat.isTransientPollError(new TypeError('Failed to fetch')), true);
  assert.equal(chat.isTransientPollError({ status: 502 }), true);
  assert.equal(chat.isTransientPollError({ status: 429 }), true);
  assert.equal(chat.isTransientPollError({ status: 401 }), false);
  assert.equal(chat.isTransientPollError({ status: 404 }), false);
});

test('backoff grows and stops growing', () => {
  assert.equal(chat.pollDelayMs(0), 1000);
  assert.equal(chat.pollDelayMs(1), 2000);
  assert.equal(chat.pollDelayMs(2), 4000);
  assert.equal(chat.pollDelayMs(20), 15000);
});

function fakeStorage() {
  const data = new Map();
  return { getItem: key => (data.has(key) ? data.get(key) : null), setItem: (key, value) => data.set(key, value), removeItem: key => data.delete(key), data };
}

test('a running job is remembered per user and forgotten when it ends', () => {
  const storage = fakeStorage();
  const job = { jobId: 'j', sessionId: 's', assistantId: 'a', requestedMode: 'auto' };
  chat.rememberActiveJob(storage, 'u1', job);
  assert.deepEqual(chat.readActiveJob(storage, 'u1'), job);
  assert.equal(chat.readActiveJob(storage, 'u2'), null);
  chat.forgetActiveJob(storage, 'u1');
  assert.equal(chat.readActiveJob(storage, 'u1'), null);
});

test('a damaged record is ignored', () => {
  const storage = fakeStorage();
  storage.setItem('corpusil-active-job:u', '{not json');
  assert.equal(chat.readActiveJob(storage, 'u'), null);
  storage.setItem('corpusil-active-job:u', '{"jobId":1}');
  assert.equal(chat.readActiveJob(storage, 'u'), null);
});

// F27, F28, restore ----------------------------------------------------------

test('a safety answer is told apart from a retrieved one', () => {
  assert.equal(chat.safetyKind({ routingReason: 'safety_emergency' }), 'emergency');
  assert.equal(chat.safetyKind({ routingReason: 'safety_refusal' }), 'refusal');
  assert.equal(chat.safetyKind({ routingReason: 'fast_keyword' }), null);
  assert.equal(chat.safetyKind({ safetyKind: 'emergency' }), 'emergency');
  assert.equal(chat.safetyKind({ safetyKind: 'something-else' }), null);
});

test('a reopened answer keeps its grades and its safety label', () => {
  const grades = [{ section: 'Why', confidence: 'strong', reason: 'two sources' }];
  const [graded, safety, old] = chat.restoreStoredMessages([
    { id: '1', role: 'assistant', content: 'a', citations: [], confidence_score: 0.9, created_at: '2026-01-01T00:00:00Z', section_confidence: grades },
    { id: '2', role: 'assistant', content: 'b', citations: [], confidence_score: 0, created_at: '2026-01-01T00:00:00Z', safety_kind: 'emergency' },
    { id: '3', role: 'user', content: 'c', citations: [], confidence_score: null, created_at: '2026-01-01T00:00:00Z' },
  ]);
  assert.deepEqual(graded.sectionConfidence, grades);
  assert.equal(graded.evidenceStrength, undefined, 'the grade was not stored, so it is not invented');
  assert.equal(chat.safetyKind(safety), 'emergency');
  assert.equal(safety.evidenceStrength, 'insufficient');
  assert.equal(old.role, 'user');
});

test('an answer with nothing behind it routes to a person', () => {
  assert.equal(chat.shouldOfferHuman({ evidenceStrength: 'insufficient', citations: [{}] }), true);
  assert.equal(chat.shouldOfferHuman({ evidenceStrength: 'strong', citations: [] }), true);
  assert.equal(chat.shouldOfferHuman({ evidenceStrength: 'strong', citations: [{}] }), false);
  assert.equal(chat.shouldOfferHuman({ error: 'failed', citations: [] }), false);
});

// F25 ------------------------------------------------------------------------

function loadApi(fetchImpl) {
  const load = createLoader({ './runtime-backend': { DEFAULT_BACKEND_URL: 'http://api.test', getRuntimeBackendUrl: () => 'http://api.test' } });
  global.fetch = fetchImpl;
  const api = load('lib/api.ts');
  const expiry = load('lib/session-expiry.ts');
  return { api, expiry };
}

const res = (status, body = {}) => ({ ok: status < 400, status, statusText: String(status), json: async () => body });

test('a refused refresh ends the session once, and the call fails plainly', async () => {
  const { api, expiry } = loadApi(async url => (String(url).includes('/auth/cookie/refresh') ? res(401) : res(401, { detail: 'Not signed in' })));
  let events = 0;
  const stop = expiry.onSessionExpired(() => { events += 1; });
  await assert.rejects(api.request('/citizen/matter/deadlines'), /Not signed in/);
  stop();
  assert.equal(events, 1);
});

test('a network failure during refresh does not sign anyone out', async () => {
  const { api, expiry } = loadApi(async url => {
    if (String(url).includes('/auth/cookie/refresh')) throw new TypeError('Failed to fetch');
    return res(401, { detail: 'Not signed in' });
  });
  let events = 0;
  const stop = expiry.onSessionExpired(() => { events += 1; });
  await assert.rejects(api.request('/citizen/matter/deadlines'));
  stop();
  assert.equal(events, 0);
});

test('a successful refresh retries the call and does not sign anyone out', async () => {
  let calls = 0;
  const { api, expiry } = loadApi(async url => {
    if (String(url).includes('/auth/cookie/refresh')) return res(200);
    calls += 1;
    return calls === 1 ? res(401) : res(200, { items: [] });
  });
  let events = 0;
  const stop = expiry.onSessionExpired(() => { events += 1; });
  assert.deepEqual(await api.request('/citizen/matter/deadlines'), { items: [] });
  stop();
  assert.equal(events, 0);
});

test('a sign-in failure is never treated as an expired session', async () => {
  let refreshed = false;
  const { api, expiry } = loadApi(async url => {
    if (String(url).includes('/auth/cookie/refresh')) { refreshed = true; return res(401); }
    return res(401, { detail: 'Wrong password' });
  });
  let events = 0;
  const stop = expiry.onSessionExpired(() => { events += 1; });
  await assert.rejects(api.login('a@b.c', 'x'), /Wrong password/);
  stop();
  assert.equal(refreshed, false);
  assert.equal(events, 0);
});

test('a draft survives until it is sent', () => {
  const storage = fakeStorage();
  chat.saveDraft(storage, 'half a question');
  assert.equal(chat.readDraft(storage), 'half a question');
  chat.saveDraft(storage, '');
  assert.equal(chat.readDraft(storage), '');
});

// F11 ------------------------------------------------------------------------

test('a repealed source shows what replaced it and when', () => {
  const view = currencyView({ repeal_label: 'no_longer_in_force', repealed_on: '2024-07-01', replaced_by: 'BNSS' });
  assert.deepEqual(view, { kind: 'repealed', repealedOn: '2024-07-01', replacedBy: 'BNSS' });
});

test('a source that cites moved provisions shows the mappings', () => {
  const mappings = [{ from_code: 'CrPC', from_section: '154', to_code: 'BNSS', to_section: '173' }];
  const view = currencyView({ repeal_label: 'concerns_repealed_provision', section_mappings: mappings, unmapped_repealed_provisions: ['IPC s.1'], mapping_review_status: 'pending_legal_review' });
  assert.equal(view.kind, 'moved');
  assert.deepEqual(view.mappings, mappings);
  assert.deepEqual(view.unmapped, ['IPC s.1']);
  assert.equal(view.pendingReview, true);
});

test('a current source shows no warning', () => {
  assert.deepEqual(currencyView({ repeal_label: 'none' }), { kind: 'none' });
  assert.deepEqual(currencyView({}), { kind: 'none' });
});

test('only a web address becomes a source link', () => {
  assert.equal(safeSourceUrl('https://www.mha.gov.in/x.pdf'), 'https://www.mha.gov.in/x.pdf');
  assert.equal(safeSourceUrl('javascript:alert(1)'), null);
  assert.equal(safeSourceUrl('not a url'), null);
  assert.equal(safeSourceUrl(null), null);
});

// C-10 -----------------------------------------------------------------------

const DEADLINE = { id: 'abc', title: 'Reply, to notice; today', due_on: '2026-03-01', remind_days_before: 7, notes: 'Line one\nLine two', provision_label: 'NI s.138' };

test('the calendar file is valid and carries the reminder', () => {
  const ics = buildIcs(DEADLINE, new Date('2026-01-01T10:00:00Z'));
  assert.match(ics, /^BEGIN:VCALENDAR\r\n/);
  assert.match(ics, /DTSTART;VALUE=DATE:20260301\r\n/);
  assert.match(ics, /DTEND;VALUE=DATE:20260302\r\n/);
  assert.match(ics, /TRIGGER:-P7D\r\n/);
  assert.match(ics, /SUMMARY:Reply\\, to notice\\; today\r\n/, 'commas and semicolons are escaped');
  assert.match(ics, /END:VCALENDAR\r\n$/);
  for (const line of ics.split('\r\n')) assert.ok(line.length <= 75, line);
});

test('a month-end date rolls over properly', () => {
  assert.match(buildIcs({ ...DEADLINE, due_on: '2026-12-31' }), /DTEND;VALUE=DATE:20270101/);
});

test('only what needs attention is surfaced', () => {
  const items = ['overdue', 'due_today', 'due_soon', 'upcoming', 'done'].map(status => ({ status, days_left: 0 }));
  assert.deepEqual(needsAttention(items).map(item => item.status), ['overdue', 'due_today', 'due_soon']);
});

test('the status reads in words', () => {
  const words = { done: 'Done', today: 'Today', overdue: days => `${days} late`, left: days => `${days} left` };
  assert.equal(dueLabel({ status: 'done', days_left: -9 }, words), 'Done');
  assert.equal(dueLabel({ status: 'due_today', days_left: 0 }, words), 'Today');
  assert.equal(dueLabel({ status: 'overdue', days_left: -3 }, words), '3 late');
  assert.equal(dueLabel({ status: 'due_soon', days_left: 4 }, words), '4 left');
});

// C-04 offline ---------------------------------------------------------------

test('the page hands over its own assets and nothing from anywhere else', () => {
  const urls = assetsToCache(['http://x.test/_next/static/chunks/a.js', 'http://x.test/_next/static/css/b.css', 'http://x.test/citizen/matter/deadlines', 'http://other.test/_next/static/c.js', 'nonsense'], 'http://x.test');
  assert.deepEqual(urls, ['/rights', '/_next/static/chunks/a.js', '/_next/static/css/b.css']);
});

function runWorker() {
  const handlers = {};
  const store = new Map();
  const cacheApi = { put: async (key, value) => { store.set(key.url ?? key, value); }, addAll: async () => {} };
  const context = {
    self: { addEventListener: (name, fn) => { handlers[name] = fn; }, location: { origin: 'http://x.test' }, skipWaiting: () => {}, clients: { claim: async () => {} } },
    caches: { open: async () => cacheApi, match: async key => store.get(key.url ?? key), keys: async () => [], delete: async () => true },
    fetch: async () => { throw new TypeError('offline'); },
    URL,
    Response: { error: () => ({ type: 'error' }) },
    Promise,
  };
  vm.runInNewContext(fs.readFileSync(path.join(ROOT, 'public/citizen-offline-sw.js'), 'utf8'), context);
  const dispatch = request => {
    let responded = null;
    handlers.fetch({ request, respondWith: value => { responded = value; } });
    return responded;
  };
  return { dispatch, store };
}

test('the worker only touches the rights page and static assets', async () => {
  const { dispatch } = runWorker();
  for (const url of ['http://x.test/', 'http://x.test/citizen/matter/deadlines', 'http://x.test/chat/sessions', 'http://other.test/rights']) {
    assert.equal(dispatch({ method: 'GET', url }), null, url);
  }
  assert.equal(dispatch({ method: 'POST', url: 'http://x.test/rights' }), null);
  const page = dispatch({ method: 'GET', url: 'http://x.test/rights' });
  const asset = dispatch({ method: 'GET', url: 'http://x.test/_next/static/chunks/a.js' });
  assert.notEqual(page, null);
  assert.notEqual(asset, null);
  await Promise.allSettled([page, asset]); // offline in this test, so the asset fetch fails
});

test('offline, the rights page comes from the cache', async () => {
  const { dispatch, store } = runWorker();
  store.set('/rights', { body: 'saved page' });
  assert.deepEqual(await dispatch({ method: 'GET', url: 'http://x.test/rights' }), { body: 'saved page' });
});

// Themes ---------------------------------------------------------------------

test('citizen components and styles use tokens, so both themes work', () => {
  const dir = path.join(ROOT, 'components/citizen');
  for (const name of fs.readdirSync(dir)) {
    const source = fs.readFileSync(path.join(dir, name), 'utf8');
    assert.deepEqual(source.match(/#[0-9a-fA-F]{6}\b/g) ?? [], [], name);
    assert.equal(/\bbg-white\b/.test(source), false, name);
  }
  const css = fs.readFileSync(path.join(ROOT, 'app/citizen.css'), 'utf8').replace(/box-shadow:[^;}]*/g, '');
  assert.deepEqual(css.match(/#[0-9a-fA-F]{3,8}\b/g) ?? [], [], 'only a shadow may be a literal');
});
