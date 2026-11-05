const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const loadTs = require('./load-ts.cjs');
const { followUpTopic, citizenFollowUps, professionalFollowUps, ALL_PROFESSIONAL_QUESTIONS, MAX_FOLLOW_UPS } = loadTs('lib/follow-ups.ts');

const cited = (act_name, over = {}) => ({ act_name, title: act_name, ...over });
const plain = value => [...value];

// Language that would imply the product can say how a matter ends.
const OUTCOME = /\b(win|wins|won|lose|chance|chances|likely|likelihood|odds|prospects?|outcome|verdict|succeed|convict\w*|acquit\w*|guilty|will the (court|judge)|get bail)\b/i;

test('the topic comes from what the answer cited', () => {
  assert.equal(followUpTopic([cited('Bharatiya Nagarik Suraksha Sanhita, 2023')]), 'procedure');
  assert.equal(followUpTopic([cited('Indian Penal Code, 1860')]), 'offence');
  assert.equal(followUpTopic([cited('Bharatiya Sakshya Adhiniyam, 2023')]), 'evidence');
  assert.equal(followUpTopic([cited('Constitution of India')]), 'rights');
  assert.equal(followUpTopic([cited('Consumer Protection Act, 2019')]), 'consumer');
  assert.equal(followUpTopic([cited('Some Other Act, 2001')]), 'general');
  assert.equal(followUpTopic([]), 'general');
});

test('the most cited topic wins, and the same citations always give the same answer', () => {
  const citations = [cited('Indian Penal Code, 1860'), cited('Code of Criminal Procedure, 1973'), cited('Code of Criminal Procedure, 1973')];
  assert.equal(followUpTopic(citations), 'procedure');
  assert.deepEqual(plain(citizenFollowUps(citations)), plain(citizenFollowUps(citations)));
});

test('each role gets its own list, capped', () => {
  const citations = [cited('Bharatiya Nyaya Sanhita, 2023')];
  const police = plain(professionalFollowUps('police', citations));
  const advocate = plain(professionalFollowUps('advocate', citations));
  assert.notDeepEqual(police, advocate);
  assert.ok(police.length <= MAX_FOLLOW_UPS);
  assert.ok(advocate.length <= MAX_FOLLOW_UPS);
});

test('a renumbered provision brings the question about what differs', () => {
  const [first, ...rest] = professionalFollowUps('advocate', [cited('Indian Penal Code, 1860', { section_mappings: [{}] })]);
  assert.match(first, /earlier provision/);
  assert.equal(rest.length, MAX_FOLLOW_UPS - 1);
});

test('no suggestion implies a prediction, in any language', () => {
  for (const question of ALL_PROFESSIONAL_QUESTIONS) assert.doesNotMatch(question, OUTCOME, question);
  const source = fs.readFileSync('lib/citizen-i18n.ts', 'utf8');
  const lines = source.split('\n').filter(line => /^\s*fu[A-Z]\w*: l\(/.test(line));
  assert.ok(lines.length >= 12, 'the citizen questions are in the file');
  for (const line of lines) {
    assert.doesNotMatch(line, OUTCOME, line);
    // Win, lose and chance, in the two translated languages. "व्यवहार" (practice) ends in हार, so that word is looked for with its verb endings.
    assert.doesNotMatch(line, /जीत|हारन|हारें|हार ज|संभावना|గెల|ఓడి|అవకాశ/, line);
  }
});

test('every citizen question exists in all three languages', () => {
  const { UI } = loadTs('lib/citizen-i18n.ts', { require: () => ({ l: (en, hi, te) => ({ en, hi, te }), LANGS: ['en', 'hi', 'te'] }), Object });
  for (const topic of [[], [cited('Indian Penal Code')], [cited('Bharatiya Sakshya Adhiniyam')], [cited('Bharatiya Nagarik Suraksha Sanhita')], [cited('Constitution of India')], [cited('Consumer Protection Act')]]) {
    for (const key of citizenFollowUps(topic)) {
      assert.ok(UI[key], key);
      for (const lang of ['en', 'hi', 'te']) assert.ok(UI[key][lang], `${key} ${lang}`);
    }
  }
});

test('choosing a question fills the composer and does not send it', () => {
  const component = fs.readFileSync('components/FollowUps.tsx', 'utf8');
  assert.doesNotMatch(component, /onSend|submit\(/);
  const composer = fs.readFileSync('components/ChatInput.tsx', 'utf8');
  assert.match(composer, /FILL_COMPOSER_EVENT/);
});
