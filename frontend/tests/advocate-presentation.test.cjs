const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');

const moduleScope = { exports: {} };
vm.runInNewContext(
  ts.transpileModule(fs.readFileSync('lib/advocate-presentation.ts', 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText,
  moduleScope,
);
const p = moduleScope.exports;

test('a blank tri-state is not recorded, not no', () => {
  assert.equal(p.triState(''), null);
  assert.equal(p.triState('no'), false);
  assert.equal(p.triState('yes'), true);
});

test('an empty bail form sends unknowns as null, so the server names them as missing', () => {
  const body = p.bailRequest(p.EMPTY_BAIL_FORM, false);
  for (const key of ['punishable_with_death_or_life', 'max_punishment_months', 'first_remand_on', 'report_filed', 'other_cases_pending', 'first_time_offender']) {
    assert.equal(body[key], null, key);
  }
  assert.equal(body.classification, 'unknown');
  assert.equal(body.gravity, 'unknown');
  assert.equal(body.delay_by_accused_days, 0);
});

test('punishment in years reaches the server in months, including a half year', () => {
  const body = p.bailRequest({ ...p.EMPTY_BAIL_FORM, maxPunishmentYears: '7.5' }, true);
  assert.equal(body.max_punishment_months, 90);
  assert.equal(body.save, true);
  assert.equal(p.bailRequest({ ...p.EMPTY_BAIL_FORM, maxPunishmentYears: '' }, false).max_punishment_months, null);
  assert.equal(p.bailRequest({ ...p.EMPTY_BAIL_FORM, maxPunishmentYears: 'life' }, false).max_punishment_months, null);
});

test('an unknown route status reads as undetermined, never as favourable', () => {
  assert.deepEqual({ ...p.routeStatusMeta('anything-new') }, { label: 'Not determined', tone: 'warn' });
  assert.equal(p.routeStatusMeta('barred_on_text').tone, 'bad');
});

test('no route status label predicts an outcome', () => {
  for (const status of ['entitled_on_text', 'discretionary', 'barred_on_text', 'not_yet', 'needs_review', 'undetermined', 'not_applicable']) {
    assert.doesNotMatch(p.routeStatusMeta(status).label, /will|win|granted|likely|eligible/i);
  }
});

test('events sort by urgency before date', () => {
  const sorted = p.sortEvents([
    { state: 'upcoming', due_on: '2026-12-01' },
    { state: 'done', due_on: '2020-01-01' },
    { state: 'overdue', due_on: '2026-10-01' },
    { state: 'due_today', due_on: '2026-11-04' },
    { state: 'due_soon', due_on: '2026-11-06' },
    { state: 'overdue', due_on: '2026-09-01' },
  ]);
  assert.deepEqual([...sorted.map((item) => item.due_on)], ['2026-09-01', '2026-10-01', '2026-11-04', '2026-11-06', '2026-12-01', '2020-01-01']);
});

test('day phrases read naturally on both sides of today', () => {
  assert.equal(p.dayPhrase(0), 'today');
  assert.equal(p.dayPhrase(1), 'tomorrow');
  assert.equal(p.dayPhrase(-1), 'yesterday');
  assert.equal(p.dayPhrase(-5), '5 days ago');
  assert.equal(p.dayPhrase(12), 'in 12 days');
});

test('dates do not shift by timezone and an absent date says so', () => {
  assert.equal(p.formatDate('2026-03-02'), '2 Mar 2026');
  assert.equal(p.formatDate('2026-01-01T00:00:00Z'), '1 Jan 2026');
  assert.equal(p.formatDate(null), 'Not recorded');
});

test('a repealed source is labelled as repealed and names its successor', () => {
  const label = p.currencyMeta({ current_status: 'repealed', repeal_label: 'no_longer_in_force', replaced_by: 'BNSS' });
  assert.equal(label.tone, 'bad');
  assert.match(label.label, /Repealed.*BNSS/);
});

test('an in-force document citing moved provisions is not called repealed', () => {
  const label = p.currencyMeta({ current_status: 'current', repeal_label: 'concerns_repealed_provision' });
  assert.equal(label.label, 'Cites renumbered provisions');
});

test('a currency label nobody recognises reads as unverified, never in force', () => {
  assert.equal(p.currencyMeta({ current_status: 'something' }).label, 'Currency not verified');
  assert.equal(p.currencyMeta({}).tone, 'warn');
  assert.equal(p.currencyMeta({ current_status: 'current', repeal_label: 'none' }).label, 'In force');
});

test('work kinds have readable labels and known views', () => {
  assert.equal(p.workKindLabel('draft:bail_application'), 'Draft: bail application');
  assert.equal(p.workView('draft:reply'), 'draft');
  assert.equal(p.workView('synopsis'), 'brief');
  assert.equal(p.workView('defence_analysis'), 'defence');
  assert.equal(p.workView('from-the-future'), 'unknown');
});

test('coverage is always stated, even when the count could not be read', () => {
  const [statement, absence] = p.coverageLines(null);
  assert.match(statement, /could not be read/);
  assert.match(absence, /not evidence that none exists/);
  const [given] = p.coverageLines({ statement: 'Searched the 12 judgments this corpus holds.', absence_note: 'x' });
  assert.match(given, /12 judgments/);
});

test('the fallback wording never carries a remembered count', () => {
  const [statement] = p.coverageLines(undefined);
  assert.doesNotMatch(statement, /\d/);
});

test('debate status lines keep the finished turns in view', () => {
  assert.equal(p.debateIsActive('running'), true);
  assert.equal(p.debateIsActive('queued'), true);
  assert.equal(p.debateIsActive('failed'), false);
  assert.match(p.debateStatusLine({ status: 'queued', turns_done: 2, turns_total: 4, attempt_count: 1 }, null), /2 of 4 turns already finished are kept/);
  assert.match(p.debateStatusLine({ status: 'queued', turns_done: 0, turns_total: 4, attempt_count: 0 }, null), /starts when/);
  assert.equal(p.debateStatusLine({ status: 'running', turns_done: 1, turns_total: 4, attempt_count: 1 }, 'Round 1: checking'), 'Round 1: checking');
  assert.match(p.debateStatusLine({ status: 'failed', turns_done: 1, turns_total: 4, attempt_count: 3 }, null), /What finished is shown/);
});

test('an exported draft always carries its disclaimer, exactly once', () => {
  const disclaimer = 'DRAFT FOR REVIEW.';
  const already = p.draftExportText({ rendered_text: `${disclaimer}\n\nBody`, disclaimer });
  assert.equal(already.split(disclaimer).length - 1, 1);
  const missing = p.draftExportText({ rendered_text: 'Body', disclaimer });
  assert.ok(missing.startsWith(disclaimer));
});

test('export filenames are safe', () => {
  assert.equal(p.exportFilename('Bail application', 2), 'bail-application-v2.txt');
  assert.equal(p.exportFilename('///', 1), 'draft-v1.txt');
});

test('articles group by division in the order given', () => {
  const groups = p.groupArticles([{ division: 'Suits', k: 1 }, { division: 'Appeals', k: 2 }, { division: 'Suits', k: 3 }]);
  assert.deepEqual([...groups.map(([name, items]) => [name, items.length])], [['Suits', 2], ['Appeals', 1]]);
});

test('a debate in progress lays out its rounds, leaving the unfinished side empty', () => {
  const rounds = p.turnsByRound([{ round: 1, side: 'for' }, { round: 1, side: 'against' }, { round: 2, side: 'for' }]);
  assert.equal(rounds.length, 2);
  assert.equal(rounds[1].against, null);
  assert.equal(rounds[1].for.side, 'for');
});
