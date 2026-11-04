const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');

const moduleScope = { exports: {} };
vm.runInNewContext(
  ts.transpileModule(fs.readFileSync('lib/police-presentation.ts', 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText,
  { ...moduleScope, URLSearchParams, Date, Math, String, Object, Number },
);
const p = moduleScope.exports;

const row = (over = {}) => ({
  case_id: 'c', case_title: 't', key: 'k', obligation: 'o', provision: 'BNSS s.58', actor: 'investigating_officer',
  is_officer_duty: true, consequence: '', computed_from: '', due_at: '2026-01-01T00:00:00Z', state: 'due',
  state_reason: '', is_earliest_possible: false, is_imminent: false, completed_at: null, completion_note: '',
  completion_is_derived: false, notes: [], ...over,
});

const sectionOf = (over) => p.groupRegister([row(over)])[0].key;

test('overdue and imminent are what the officer reads first', () => {
  assert.equal(sectionOf({ state: 'overdue' }), 'act_now');
  assert.equal(sectionOf({ state: 'due', is_imminent: true }), 'act_now');
  assert.equal(p.groupRegister([row({ state: 'met' }), row({ state: 'overdue' })])[0].key, 'act_now');
});

test('sections keep their order whatever order the rows arrive in', () => {
  const keys = p.groupRegister([
    row({ state: 'met' }), row({ state: 'unknown' }), row({ state: 'breached' }),
    row({ state: 'due' }), row({ state: 'overdue' }), row({ state: 'overdue', is_officer_duty: false }),
  ]).map((s) => s.key);
  assert.equal(keys.join(), 'act_now,breached,unknown,coming_up,others,met');
});

test('cannot be determined never lands among passed or failed rows', () => {
  const sections = p.groupRegister([row({ state: 'unknown', due_at: null })]);
  assert.equal(sections.length, 1);
  assert.equal(sections[0].key, 'unknown');
  assert.equal(p.registerWords({ state: 'unknown', is_imminent: false }).label, 'Cannot be determined');
  assert.equal(p.registerWords({ state: 'unknown', is_imminent: false }).tone, 'warn');
});

test('a duty somebody else owes is not counted as the officer breaching', () => {
  assert.equal(sectionOf({ state: 'overdue', is_officer_duty: false, actor: 'magistrate' }), 'others');
  assert.equal(sectionOf({ state: 'breached', is_officer_duty: false, actor: 'magistrate' }), 'others');
  assert.equal(p.ACTOR_WORDS.magistrate, "Magistrate's duty");
});

test('every state has a word, not only a colour', () => {
  for (const state of ['breached', 'overdue', 'due', 'met', 'unknown']) {
    assert.ok(p.REGISTER_WORDS[state].label.length > 0, state);
  }
  assert.equal(p.registerWords({ state: 'due', is_imminent: true }).label, 'Due soon');
  assert.equal(p.registerWords({ state: 'due', is_imminent: false }).label, 'Due');
});

test('overdue and breached read differently', () => {
  assert.notEqual(p.REGISTER_WORDS.overdue.label, p.REGISTER_WORDS.breached.label);
});

test('the time left never flatters', () => {
  const now = Date.parse('2026-01-01T00:00:00Z');
  assert.equal(p.timeLeft('2026-01-01T05:30:00Z', now), '5 hr left');
  assert.equal(p.timeLeft('2025-12-31T23:30:00Z', now), '1 hr over');
  assert.equal(p.timeLeft('2026-01-05T00:00:00Z', now), '4 days left');
  assert.equal(p.timeLeft('2025-12-20T00:00:00Z', now), '12 days over');
});

test('the register query carries repeated states and drops empties', () => {
  const query = p.registerQuery({ states: ['overdue', 'unknown'], caseId: '', provision: '  193 ', imminentOnly: true });
  assert.equal(query, 'state=overdue&state=unknown&provision=193&imminent_only=true');
  assert.equal(p.registerQuery({}), '');
});

test('no search finding claims legality', () => {
  for (const finding of Object.values(p.FINDING_WORDS)) {
    assert.doesNotMatch(finding.label, /\b(legal|illegal|lawful|unlawful)\b/i);
  }
  assert.match(p.FINDING_WORDS.no_defect_on_record.detail, /not a ruling/);
});

test('no offence finding says the offence is made out', () => {
  assert.doesNotMatch(p.OFFENCE_FINDING_WORDS.all_elements_supported.label, /made out|proved|guilty/i);
  assert.match(p.OFFENCE_FINDING_WORDS.all_elements_supported.detail, /not a finding/);
});

test('three-state words keep unknown distinct everywhere', () => {
  for (const words of [p.CHAIN_WORDS.cannot_be_determined, p.VERDICT_WORDS.cannot_be_determined, p.ELEMENT_WORDS.cannot_be_determined]) {
    assert.equal(words.label, 'Cannot be determined');
    assert.equal(words.tone, 'warn');
  }
  assert.equal(p.TRI_WORDS.unknown, 'Not recorded');
});

test('the compliance status cycle reaches all three states', () => {
  let state = 'not_recorded';
  const seen = [];
  for (let i = 0; i < 3; i += 1) { state = p.NEXT_COMPLIANCE[state]; seen.push(state); }
  assert.deepEqual(seen, ['satisfied', 'not_satisfied', 'not_recorded']);
});

test('F22: loading and failed are not "nothing recorded"', () => {
  const loading = p.caseTimelineMessage({ kind: 'loading' });
  const failed = p.caseTimelineMessage({ kind: 'failed' });
  const none = p.caseTimelineMessage({ kind: 'none' });
  assert.notEqual(loading, failed);
  assert.notEqual(failed, none);
  assert.match(none, /No dates recorded/);
  assert.doesNotMatch(loading, /could not be read/);
});

test('F20: the scope is locked only once the chat has a session', () => {
  assert.equal(p.scopeLockedReason(null), null);
  assert.match(p.scopeLockedReason('s-1'), /Start a new chat/);
});

test('every draft type has a title and fields, and no field asks for what the record supplies', () => {
  for (const type of ['s35_3_notice', 's94_production_order', 'seizure_memo', 'case_diary_entry', 'remand_application', 'chargesheet_skeleton']) {
    assert.ok(p.DRAFT_TITLES[type]);
    assert.ok(p.DRAFT_FIELDS[type].length > 0);
    const keys = p.DRAFT_FIELDS[type].map((f) => f.key);
    assert.equal(new Set(keys).size, keys.length, type);
  }
});

test('a copied draft keeps its warning', () => {
  assert.equal(p.draftForClipboard({ rendered_text: 'x\nDRAFT warn', disclaimer: 'DRAFT warn' }), 'x\nDRAFT warn');
  assert.match(p.draftForClipboard({ rendered_text: 'x', disclaimer: 'DRAFT warn' }), /DRAFT warn$/);
});

test('a cleared field goes out as null, so a mistake can be undone', () => {
  const out = p.cleanForm({ a: ' value ', b: '  ' });
  assert.equal(out.a, 'value');
  assert.equal(out.b, null);
});

test('a time typed without a zone gains one on the way out and survives the round trip', () => {
  const iso = p.fromLocalInput('2026-03-01T10:15');
  assert.match(iso, /Z$/);
  assert.equal(p.toLocalInput(iso), '2026-03-01T10:15');
  assert.equal(p.fromLocalInput(''), null);
  assert.equal(p.toLocalInput(null), '');
});

test('nothing recorded prints as nothing recorded', () => {
  assert.equal(p.formatMoment(null), 'Not recorded');
  assert.equal(p.formatDay(''), 'Not recorded');
  assert.equal(p.formatMoment('garbage'), 'Not recorded');
});

test('only a supervisor grant counts as supervising', () => {
  const units = [{ my_role: 'member' }, { my_role: 'supervisor' }];
  assert.equal(p.supervisedUnits(units).length, 1);
  assert.equal(p.supervisedUnits([{ my_role: 'member' }]).length, 0);
});

test('counts are summed by name and a missing count is zero', () => {
  assert.equal(p.sumCounts({ overdue: 2, imminent: 1 }, ['overdue', 'imminent', 'breached']), 3);
});
