const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');
const moduleScope = { exports: {} };
vm.runInNewContext(ts.transpileModule(fs.readFileSync('lib/answer-presentation.ts', 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText, moduleScope);
const { presentAnswer, legalCategory, isFastBrief, sourceHeading, sourceStanding, deepStageIndex } = moduleScope.exports;

test('no verdict is inferred from the wording of the answer', () => {
  // The renderer must not promote the model's first word to a legal finding.
  // Every one of these previously produced a "Yes." / "No." / "It depends."
  // headline with green, maroon or amber tone.
  for (const content of [
    '## Direct answer\n\nYes, subject to the stated conditions.',
    '## Direct answer\n\nNo. This is not established.',
    '## Direct answer\n\nIt depends: facts are missing.',
    '## Direct answer\n\nRegistration is mandatory for a cognizable offence.',
  ]) {
    const result = presentAnswer(content);
    assert.equal(result.headline, 'What the sources establish.');
    assert.equal(result.abstained, false);
    assert.equal(result.tone, undefined, 'tone must no longer exist');
  }
});

test('the answer text itself is never rewritten', () => {
  const content = '## Direct answer\n\nYes, subject to the stated conditions. [Source 1]';
  assert.equal(
    presentAnswer(content).explanation,
    'Yes, subject to the stated conditions. [Source 1]',
  );
});

test('abstention is read from evidence strength, not from prose', () => {
  const rewordedAbstention = '## Direct answer\n\nThe governed corpus does not support a reliable answer here.';

  // Prose matching missed this entirely; the pipeline flag does not.
  const flagged = presentAnswer(rewordedAbstention, { evidenceStrength: 'insufficient' });
  assert.equal(flagged.abstained, true);
  assert.equal(flagged.headline, 'More evidence is needed.');

  // A supported answer is not an abstention even when it discusses limits.
  const supported = presentAnswer(
    '## Direct answer\n\nRegistration is mandatory.\n\n## Important limits\n\nEvidence of commencement is insufficient in the corpus.',
    { evidenceStrength: 'moderate' },
  );
  assert.equal(supported.abstained, false);
  assert.equal(supported.headline, 'What the sources establish.');
});

test('prose matching still covers callers with no evidence strength', () => {
  const result = presentAnswer('I could not find enough reliable support in the indexed legal corpus for this answer.');
  assert.equal(result.abstained, true);
  assert.equal(result.headline, 'More evidence is needed.');
});

test('a verified claim repeated across sections is kept in both', () => {
  // One `seen` set shared across sections deleted the second occurrence, so
  // the renderer silently overrode the verifier.
  const result = presentAnswer([
    '## Direct answer',
    '',
    'Yes, conditionally. [Source 1]',
    '',
    '## Why this is the legal position',
    '',
    '- Preserve the notice you received. [Source 1]',
    '',
    '## How this applies to you',
    '',
    '- Preserve the notice you received. [Source 1]',
    '- A second condition applies. [Source 2]',
  ].join('\n'));

  assert.equal(
    (result.basis.match(/Preserve the notice/g) || []).length,
    2,
    'a claim verified for two sections must appear in both',
  );
  assert.match(result.basis, /second condition/);
});

test('an exact duplicate within one section is still collapsed', () => {
  const result = presentAnswer([
    '## Direct answer',
    '',
    'Registration is mandatory.',
    '',
    '## Why this is the legal position',
    '',
    '- Preserve the notice. [Source 1]',
    '- Preserve the notice. [Source 1]',
  ].join('\n'));

  assert.equal((result.basis.match(/Preserve the notice/g) || []).length, 1);
});

test('fast mode is labelled as a source brief', () => {
  const result = presentAnswer(
    'A source preview.\n\n1. Exact quoted passage.\n\nCurrency notice: confirm current status.',
    { fast: true },
  );
  assert.equal(result.headline, 'Source brief.');
  assert.match(result.footer, /Currency notice/);
  assert.doesNotMatch(result.other, /Currency notice/);
});

test('disclaimers and currency notices are routed to the footer', () => {
  const result = presentAnswer('The supported answer.\n\n\\---\n\n\\*Legal decision-support information, not a substitute for advice from a qualified professional.\\*\n\nSource currency is not independently guaranteed; confirm the law in force.');
  assert.match(result.footer, /not a substitute for/);
  assert.match(result.footer, /Source currency/);
  assert.doesNotMatch(result.other, /not a substitute for/);
});

test('limits are separated from the body', () => {
  const result = presentAnswer('## Direct answer\n\nRegistration is mandatory.\n\n## Important limits\n\nCommencement is unconfirmed.');
  assert.match(result.limits, /Commencement is unconfirmed/);
  assert.doesNotMatch(result.other, /Commencement is unconfirmed/);
});

test('legal category routing', () => {
  assert.equal(legalCategory('my phone was snatched'), 'Criminal law');
  assert.equal(legalCategory('landlord withheld my deposit'), 'Property law');
  assert.equal(legalCategory('explain Article 14'), 'Constitutional law');
  assert.equal(legalCategory('what is a valid agreement'), 'Contract law');
  assert.equal(legalCategory('how do I read a statute'), 'Legal research');
});

test('a Fast brief is recognised by its opening sentence, and only by it', () => {
  assert.equal(isFastBrief('Fast evidence brief — the following governed corpus passages'), true);
  assert.equal(isFastBrief('Information may be given orally [Source 1].'), false);
});

test('a source is named by Act and section, without doubling the label', () => {
  const base = { title: 'The Code of Criminal Procedure, 1973', act_name: 'Code of Criminal Procedure, 1973' };
  assert.equal(sourceHeading({ ...base, section: 'Section 154' }).section, '154');
  assert.equal(sourceHeading({ ...base, section: '154' }).sectionIsNumber, true);
  assert.equal(sourceHeading({ ...base, section: 'Article 14' }).sectionIsNumber, false);
  assert.equal(sourceHeading({ ...base, section: null }).section, null);
  assert.equal(sourceHeading(base).detail, null);
  assert.equal(sourceHeading({ title: 'A circular', act_name: 'Some Act, 1999' }).detail, 'A circular');
});

test('where a source stands comes from its labels, and an unknown is not a pass', () => {
  assert.equal(sourceStanding({ title: 'x', current_status: 'current' }).tone, 'ok');
  assert.equal(sourceStanding({ title: 'x', current_status: 'current', repeal_label: 'no_longer_in_force' }).tone, 'bad');
  // An operative document citing a moved section is still in force: a warning, not a repeal.
  assert.equal(sourceStanding({ title: 'x', current_status: 'current', repeal_label: 'concerns_repealed_provision' }).tone, 'warn');
  assert.equal(sourceStanding({ title: 'x', current_status: 'status_unverified' }).tone, 'plain');
  assert.equal(sourceStanding({ title: 'x' }).tone, 'plain');
});

test('each stage the job reports lands on its step of the wait', () => {
  // Mirrors DEEP_STAGE_LABELS in backend/app/services/job_worker.py.
  assert.equal(deepStageIndex(null), 0);
  assert.equal(deepStageIndex('Preparing your question'), 0);
  assert.equal(deepStageIndex('Understanding your question'), 0);
  assert.equal(deepStageIndex('Searching the legal corpus'), 0);
  assert.equal(deepStageIndex('Searching again for better authority'), 0);
  assert.equal(deepStageIndex('Working through the law that applies'), 1);
  assert.equal(deepStageIndex('Checking every statement against its source'), 2);
  assert.equal(deepStageIndex('Writing your answer'), 3);
  assert.equal(deepStageIndex('Waiting in line, position 2'), -1);
});
