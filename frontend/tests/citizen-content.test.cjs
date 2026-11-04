const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { loadTs, ROOT } = require('./helpers/load-ts.cjs');

const { hasProvision, provision, LANGS } = loadTs('lib/citizen-law/law.ts');
const { RIGHTS_TOPICS, HELP_NUMBERS } = loadTs('lib/citizen-law/rights.ts');
const { SITUATIONS, NOT_COVERED_ABSTAIN, routeSituation, computeDeadline } = loadTs('lib/citizen-law/forums.ts');
const { JOURNEYS, findStep } = loadTs('lib/citizen-law/journeys.ts');
const { AID_CATEGORIES, AID_TEXT, checkLegalAid } = loadTs('lib/citizen-law/legal-aid.ts');
const { DRAFT_TEMPLATES, DRAFT_MARK, renderDraft, repealWarnings } = loadTs('lib/citizen-law/drafts.ts');
const { buildRightsHtml } = loadTs('lib/citizen-law/rights-export.ts');
const { UI, parseLang } = loadTs('lib/citizen-i18n.ts');

const isL = value => value && typeof value === 'object' && 'en' in value && 'hi' in value && 'te' in value;

function walk(value, visit, trail = 'root') {
  if (isL(value)) { visit(value, trail); return; }
  if (Array.isArray(value)) value.forEach((item, index) => walk(item, visit, `${trail}[${index}]`));
  else if (value && typeof value === 'object') for (const key of Object.keys(value)) walk(value[key], visit, `${trail}.${key}`);
}

const devanagari = /[ऀ-ॿ]/;
const telugu = /[ఀ-౿]/;

function assertTranslated(content, label) {
  let seen = 0;
  walk(content, (text, trail) => {
    if (!text.en) return; // deliberately empty on an always-abstaining route
    seen += 1;
    assert.ok(devanagari.test(text.hi), `${label} ${trail}: Hindi is missing: ${text.hi}`);
    assert.ok(telugu.test(text.te), `${label} ${trail}: Telugu is missing: ${text.te}`);
  });
  assert.ok(seen > 0, `${label}: nothing checked`);
}

function citesIn(value, found = []) {
  if (Array.isArray(value)) value.forEach(item => citesIn(item, found));
  else if (value && typeof value === 'object') {
    for (const [key, item] of Object.entries(value)) {
      if (/cites?$/i.test(key) && typeof item === 'string') found.push(item);
      else if (/cites$/i.test(key) && Array.isArray(item)) found.push(...item);
      else citesIn(item, found);
    }
  }
  return found;
}

test('every citation in every piece of content is in the verified ledger', () => {
  const all = citesIn([RIGHTS_TOPICS, HELP_NUMBERS, SITUATIONS, JOURNEYS, AID_CATEGORIES, DRAFT_TEMPLATES.map(item => ({ cites: item.cites }))]);
  assert.ok(all.length > 150, `expected a full set of citations, found ${all.length}`);
  for (const id of all) assert.ok(hasProvision(id), `not in provisions.json: ${id}`);
});

test('every explanation exists in Hindi and Telugu', () => {
  assertTranslated(RIGHTS_TOPICS, 'rights');
  assertTranslated(HELP_NUMBERS, 'numbers');
  assertTranslated(SITUATIONS, 'router');
  assertTranslated(NOT_COVERED_ABSTAIN, 'abstain');
  assertTranslated(JOURNEYS, 'journeys');
  assertTranslated(AID_CATEGORIES, 'aid');
  assertTranslated(AID_TEXT, 'aid text');
  assertTranslated(DRAFT_TEMPLATES.map(({ title, blurb, guidance, fields }) => ({ title, blurb, guidance, fields })), 'drafts');
  assertTranslated(UI, 'interface');
});

test('every right cites at least one provision', () => {
  for (const topic of RIGHTS_TOPICS) {
    assert.ok(topic.points.length >= 4, topic.id);
    for (const point of topic.points) assert.ok(point.cites.length, `${topic.id}/${point.id} has no citation`);
  }
  assert.deepEqual(RIGHTS_TOPICS.map(topic => topic.id), ['arrest', 'stop', 'summons', 'search', 'report']);
});

test('a quote carries the provision and an official source', () => {
  const card = provision('bnss-47-1');
  assert.equal(card.label, 'BNSS s.47(1)');
  assert.match(card.quote, /full particulars of the offence/);
  assert.match(card.sourceUrl, /^https:\/\//);
  assert.throws(() => provision('bnss-999'));
});

test('quoted law is never translated: quotes exist only in the ledger, in English', () => {
  const ledger = JSON.parse(fs.readFileSync(path.join(ROOT, 'lib/citizen-law/provisions.json'), 'utf8'));
  for (const [id, entry] of Object.entries(ledger.provisions)) {
    assert.equal(devanagari.test(entry.quote) || telugu.test(entry.quote), false, id);
  }
  const shared = fs.readFileSync(path.join(ROOT, 'components/citizen/shared.tsx'), 'utf8');
  assert.match(shared, /<blockquote lang="en">/, 'quotes must be marked as English so the page language does not claim them');
});

test('nothing in the content predicts an outcome', () => {
  const words = /\byou will (win|lose)\b|\bchances? of\b|\blikely to (win|succeed)\b|\bguarantee/i;
  walk([RIGHTS_TOPICS, SITUATIONS, JOURNEYS, AID_TEXT], (text, trail) => assert.equal(words.test(text.en), false, trail));
});

// --- forum and limitation router -------------------------------------------

test('every route shows a forum and a cost, each with its basis, or abstains', () => {
  for (const situation of SITUATIONS) {
    if (situation.alwaysAbstain) continue;
    assert.ok(situation.forum.en, situation.id);
    assert.ok(situation.forumCites.length, `${situation.id} forum has no provision`);
    assert.ok(situation.cost.en, situation.id);
    assert.ok(situation.rules.length || situation.noPeriod, `${situation.id} says nothing about time`);
    for (const rule of situation.rules) assert.ok(rule.cites.length, `${situation.id}/${rule.id}`);
  }
});

test('not sure always abstains, on every gating question', () => {
  for (const situation of SITUATIONS) {
    for (const [index, question] of situation.questions.entries()) {
      const answers = Object.fromEntries(situation.questions.slice(0, index).map(item => [item.id, item.proceedOn]));
      answers[question.id] = 'unsure';
      const result = routeSituation(situation.id, answers);
      assert.equal(result.status, 'abstain', `${situation.id}/${question.id}`);
      assert.ok(result.reason.en);
    }
  }
});

test('the wrong answer abstains and the right answers route', () => {
  assert.equal(routeSituation('consumer', { 'own-use': 'no' }).status, 'abstain');
  assert.equal(routeSituation('consumer', {}).status, 'questions');
  assert.equal(routeSituation('consumer', { 'own-use': 'yes' }).status, 'route');
  assert.equal(routeSituation('cheque', { debt: 'yes', reason: 'no' }).status, 'abstain');
  assert.equal(routeSituation('cheque', { debt: 'yes', reason: 'yes', 'in-time': 'yes' }).status, 'route');
});

test('anything outside the table abstains and names a person to call', () => {
  for (const id of [null, 'property', 'accident']) {
    const result = routeSituation(id, {});
    assert.equal(result.status, 'abstain');
    assert.match(result.reason.en, /15100/);
  }
});

test('someone not safe is sent to 112, not to a form', () => {
  const result = routeSituation('domestic-violence', { 'safe-now': 'no' });
  assert.equal(result.status, 'abstain');
  assert.match(result.reason.en, /112/);
});

test('a tenancy question never names a forum', () => {
  const result = routeSituation('tenant', {});
  assert.equal(result.status, 'abstain');
  assert.equal(result.situation.rules.length, 0);
  assert.ok(result.situation.notes.length);
});

const rule = (situationId, ruleId) => SITUATIONS.find(item => item.id === situationId).rules.find(item => item.id === ruleId);

test('the periods match the provisions they cite', () => {
  // Limitation Act Art. 55 and Art. 19: three years. CPA s.69(1): two years.
  // NI s.138(b): thirty days. RTI s.19(1): thirty, s.19(3): ninety. CPA s.41: forty-five.
  // Workplace Act s.9(1): three months.
  assert.equal(computeDeadline(rule('money', 'breach'), '2024-03-15'), '2027-03-15');
  assert.equal(computeDeadline(rule('money', 'loan'), '2024-03-15'), '2027-03-15');
  assert.equal(computeDeadline(rule('consumer', 'consumer-complaint'), '2024-03-15'), '2026-03-15');
  assert.equal(computeDeadline(rule('consumer', 'consumer-appeal'), '2026-01-01'), '2026-02-15');
  assert.equal(computeDeadline(rule('cheque', 'cheque-notice'), '2026-01-10'), '2026-02-09');
  assert.equal(computeDeadline(rule('rti', 'rti-first-appeal'), '2026-01-10'), '2026-02-09');
  assert.equal(computeDeadline(rule('rti', 'rti-second-appeal'), '2026-01-01'), '2026-04-01');
  assert.equal(computeDeadline(rule('workplace', 'posh-complaint'), '2026-01-15'), '2026-04-15');
});

test('the cheque complaint runs one month after the fifteen days end', () => {
  // NI s.138(c) then s.142(1)(b). Notice received 1 Jan: fifteen days end 16 Jan.
  assert.equal(computeDeadline(rule('cheque', 'cheque-complaint'), '2026-01-01'), '2026-02-16');
});

test('a month that runs short takes the earlier day, never a later one', () => {
  assert.equal(computeDeadline({ add: { months: 1 } }, '2026-01-31'), '2026-02-28');
  assert.equal(computeDeadline({ add: { years: 2 } }, '2024-02-29'), '2026-02-28');
});

test('a bad date gives no date', () => {
  assert.equal(computeDeadline({ add: { days: 1 } }, 'not-a-date'), null);
  assert.equal(computeDeadline({ add: { days: 1 } }, '2026-02-31'), null);
});

// --- journeys ---------------------------------------------------------------

test('there is a journey for each situation people arrive with', () => {
  assert.deepEqual(JOURNEYS.map(item => item.id).sort(), ['arrested-relative', 'cheque-bounce', 'consumer-defect', 'cyber-fraud', 'domestic-violence', 'tenant', 'workplace-harassment']);
});

test('every path through every journey ends in a tool, a question or a person', () => {
  for (const journey of JOURNEYS) {
    const seen = new Set();
    const visit = id => {
      const step = findStep(journey, id);
      assert.ok(step, `${journey.id}: dangling step ${id}`);
      if (seen.has(id)) return;
      seen.add(id);
      if (step.options?.length) step.options.forEach(option => visit(option.next));
      else assert.ok(step.tools?.length || step.ask, `${journey.id}/${id} is a dead end`);
    };
    visit(journey.start);
    assert.equal(seen.size, journey.steps.length, `${journey.id}: unreachable step`);
  }
});

test('every tool a journey links to exists', () => {
  const situations = new Set(SITUATIONS.map(item => item.id));
  const templates = new Set(DRAFT_TEMPLATES.map(item => item.id));
  const topics = new Set(RIGHTS_TOPICS.map(item => item.id));
  for (const journey of JOURNEYS) for (const step of journey.steps) for (const tool of step.tools ?? []) {
    if (tool.to.tool === 'router') assert.ok(situations.has(tool.to.situation), tool.to.situation);
    if (tool.to.tool === 'draft') assert.ok(templates.has(tool.to.template), tool.to.template);
    if (tool.to.tool === 'rights') assert.ok(topics.has(tool.to.topic), tool.to.topic);
  }
});

test('the domestic violence journey asks about safety first and gives the emergency number', () => {
  const journey = JOURNEYS.find(item => item.id === 'domestic-violence');
  assert.equal(journey.start, 'safe');
  const danger = findStep(journey, 'danger');
  assert.equal(danger.emergency, true);
  assert.match(danger.title.en, /112/);
});

// --- legal aid --------------------------------------------------------------

test('legal aid covers every clause of section 12', () => {
  assert.deepEqual(AID_CATEGORIES.map(item => item.clause), ['s.12(a)', 's.12(b)', 's.12(c)', 's.12(d)', 's.12(e)', 's.12(f)', 's.12(g)', 's.12(h)']);
});

test('a category gives "may qualify", and always shows the condition in s.13', () => {
  const result = checkLegalAid(['woman-child']);
  assert.equal(result.status, 'may_qualify');
  assert.ok(result.cites.includes('lsa-12-c') && result.cites.includes('lsa-13-1'));
  assert.doesNotMatch(AID_TEXT.mayQualify.en, /you are entitled/i);
});

test('income alone never gets a yes or no, because each State sets its own figure', () => {
  const result = checkLegalAid(['income']);
  assert.equal(result.status, 'income_only');
  assert.match(AID_TEXT.incomeOnly.en, /will not tell you/);
  assert.doesNotMatch(AID_TEXT.incomeOnly.en, /nine thousand|lakh|₹/);
});

test('nothing selected still points to a person', () => {
  assert.equal(checkLegalAid([]).status, 'none_selected');
  assert.match(AID_TEXT.noneSelected.en, /15100/);
});

// --- drafts -----------------------------------------------------------------

test('there are the planned templates', () => {
  assert.deepEqual(DRAFT_TEMPLATES.map(item => item.id), ['police_complaint', 'rti', 'consumer', 'legal_notice', 'cheque_notice']);
});

test('every draft is marked as a draft at both ends', () => {
  for (const template of DRAFT_TEMPLATES) {
    const { text } = renderDraft(template, {});
    assert.ok(text.startsWith(DRAFT_MARK), template.id);
    assert.ok(text.trimEnd().endsWith(DRAFT_MARK), template.id);
  }
});

test('facts go in, and an empty field stays a visible blank', () => {
  const template = DRAFT_TEMPLATES.find(item => item.id === 'rti');
  const { text, blanks, complete } = renderDraft(template, { name: 'Asha', information: 'Copy of the file note' });
  assert.match(text, /Name: Asha/);
  assert.match(text, /Copy of the file note/);
  assert.match(text, /\[BLANK: Public authority \(the office\)\]/);
  assert.ok(blanks.includes('authority'));
  assert.equal(complete, false);
});

test('a filled draft has no blanks, and names only the law it should', () => {
  const template = DRAFT_TEMPLATES.find(item => item.id === 'cheque_notice');
  const values = Object.fromEntries(template.fields.map(field => [field.id, 'x']));
  const { text, blanks, complete } = renderDraft(template, values);
  assert.deepEqual(blanks, []);
  assert.equal(complete, true);
  assert.match(text, /section 138 of the Negotiable Instruments Act, 1881/);
  assert.match(text, /within fifteen days/);
  assert.doesNotMatch(text, /\bIPC\b|Cr\.?P\.?C/);
});

test('a template names no repealed code in its own words', () => {
  for (const template of DRAFT_TEMPLATES) {
    assert.deepEqual(repealWarnings(renderDraft(template, {}).text), [], template.id);
  }
});

test('typing a repealed code raises a labelled warning with its repeal provision', () => {
  assert.equal(repealWarnings('booked under IPC 420')[0].cite, 'bns-358');
  assert.equal(repealWarnings('section 154 CrPC')[0].cite, 'bnss-531');
  assert.equal(repealWarnings('section 318 BNS').length, 0);
});

// --- the saved offline copy --------------------------------------------------

test('the saved copy is self-contained and carries the law in English in every language', () => {
  for (const lang of LANGS) {
    const html = buildRightsHtml(lang);
    assert.match(html, new RegExp(`<html lang="${lang}">`));
    assert.doesNotMatch(html, /<script|src=|https?:\/\/(?!schema)/, 'no scripts and no network');
    assert.match(html, /BNSS s\.47\(1\)/);
    assert.match(html, /full particulars of the offence/);
    assert.match(html, /tel:15100/);
  }
  assert.ok(devanagari.test(buildRightsHtml('hi')));
  assert.ok(telugu.test(buildRightsHtml('te')));
});

test('an unknown stored language falls back to English', () => {
  assert.equal(parseLang('hi'), 'hi');
  assert.equal(parseLang('fr'), 'en');
  assert.equal(parseLang(null), 'en');
});
