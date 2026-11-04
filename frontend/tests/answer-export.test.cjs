const test = require('node:test');
const assert = require('node:assert/strict');
const loadTs = require('./load-ts.cjs');
const { answerToMarkdown, answerToHtml, safeSourceUrl, citationCurrency, citationLocation, bodyToHtml, NOT_ADVICE, exportFilename } =
  loadTs('lib/answer-export.ts');

const citation = (over = {}) => ({
  number: 1,
  chunk_id: 'c1',
  title: 'The Bharatiya Nagarik Suraksha Sanhita, 2023',
  source_type: 'act',
  page_start: 52,
  page_end: 53,
  section: '173',
  source_url: 'https://www.mha.gov.in/example.pdf',
  excerpt: 'Every information relating to the commission of a cognizable offence…',
  verification_status: 'verified',
  current_status: 'current',
  ...over,
});

const answer = (over = {}) => ({
  question: 'Can I report by message?',
  message: {
    content: '## Direct answer\n\nYes, by electronic communication [Source 1].',
    citations: [citation()],
    evidenceStrength: 'moderate',
    responseMode: 'deep',
    ...over,
  },
  exportedAt: new Date('2026-11-04T10:00:00Z'),
});

test('markdown keeps the marker, and the source it points to', () => {
  const output = answerToMarkdown(answer());
  assert.match(output, /\[Source 1\]\./);
  assert.match(output, /\*\*\[Source 1\] The Bharatiya Nagarik Suraksha Sanhita, 2023\*\*/);
  assert.match(output, /Section 173, pages 52–53/);
  assert.match(output, /https:\/\/www\.mha\.gov\.in\/example\.pdf/);
  assert.match(output, /^> Every information relating/m);
});

test('both formats carry the question and the information-not-advice note', () => {
  for (const output of [answerToMarkdown(answer()), answerToHtml(answer())]) {
    assert.ok(output.includes('Can I report by message?'));
    assert.ok(output.includes(NOT_ADVICE));
  }
});

test('the grade travels with the answer, so an export cannot read as more certain', () => {
  assert.match(answerToMarkdown(answer({ evidenceStrength: 'strong' })), /High confidence/);
  assert.match(answerToMarkdown(answer({ evidenceStrength: 'insufficient' })), /Limited evidence/);
  assert.match(answerToMarkdown(answer({ responseMode: 'fast' })), /claims not verified/);
  assert.match(answerToHtml(answer({ evidenceStrength: undefined, responseMode: undefined })), /Grade not recorded/);
});

test('an answer with no sources says so rather than leaving a blank heading', () => {
  assert.match(answerToMarkdown(answer({ citations: [] })), /No authority was cited/);
  assert.match(answerToHtml(answer({ citations: undefined })), /No authority was cited/);
});

test('repealed law says what replaced it in both formats', () => {
  const repealed = citation({
    current_status: 'repealed',
    repeal_label: 'no_longer_in_force',
    repealed_on: '2024-07-01',
    replaced_by: 'BNSS',
    section_mappings: [{ from_code: 'CrPC', from_section: '154', to_code: 'BNSS', to_section: '173' }],
  });
  const notes = citationCurrency(repealed);
  assert.match(notes[0], /No longer in force \(repealed 2024-07-01\)\. Replaced by BNSS\./);
  assert.match(notes[1], /CrPC s\.154 is now BNSS s\.173/);
  for (const output of [answerToMarkdown(answer({ citations: [repealed] })), answerToHtml(answer({ citations: [repealed] }))]) {
    assert.ok(output.includes('No longer in force'));
    assert.ok(output.includes('CrPC s.154 is now BNSS s.173'));
  }
});

test('a different offence is not presented as a renumbering', () => {
  const notes = citationCurrency(citation({
    section_mappings: [{ from_code: 'IPC', from_section: '1', to_code: 'BNS', to_section: '2', ingredients_changed: true }],
  }));
  assert.match(notes[0], /different offence/);
});

test('a single page reads as one page', () => {
  assert.equal(citationLocation(citation({ page_start: 3, page_end: 3, section: null })), 'page 3');
});

test('nothing hostile in an answer or a source survives into the html', () => {
  const output = answerToHtml({
    question: '<img src=x onerror=alert(1)>',
    message: {
      content: 'Text <script>alert(1)</script> and [click](javascript:alert(1))\n\n<b onmouseover="x">y</b>',
      citations: [citation({
        title: '<script>t</script>',
        excerpt: '</blockquote><script>e</script>',
        source_url: 'javascript:alert(1)',
      })],
    },
  });
  assert.doesNotMatch(output, /<script/);
  assert.doesNotMatch(output, /<img/);
  assert.doesNotMatch(output, /<b onmouseover/);
  assert.doesNotMatch(output, /href="javascript/);
  assert.match(output, /&lt;script&gt;/);
});

test('the saved file cannot load anything or run anything', () => {
  const output = answerToHtml(answer());
  assert.match(output, /Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"/);
  assert.doesNotMatch(output, /<script|<link|src=/);
});

test('source markers link to their source within the file', () => {
  const output = answerToHtml(answer());
  assert.match(output, /<a href="#source-1">\[Source 1\]<\/a>/);
  assert.match(output, /id="source-1"/);
});

test('only web links are kept', () => {
  assert.equal(safeSourceUrl('https://example.gov.in/a.pdf'), 'https://example.gov.in/a.pdf');
  assert.equal(safeSourceUrl('javascript:alert(1)'), null);
  assert.equal(safeSourceUrl('data:text/html,x'), null);
  assert.equal(safeSourceUrl('not a url'), null);
  assert.equal(safeSourceUrl(null), null);
});

test('the small markdown subset renders, and a list closes before a paragraph', () => {
  const html = bodyToHtml('### Heading\n\n- one\n- **two**\n\nAfter\n\n1. first\n2. second');
  assert.match(html, /<h3>Heading<\/h3>/);
  assert.match(html, /<ul><li>one<\/li><li><strong>two<\/strong><\/li><\/ul>/);
  assert.match(html, /<p>After<\/p>/);
  assert.match(html, /<ol><li>first<\/li><li>second<\/li><\/ol>/);
});

test('the filename carries no part of the question', () => {
  assert.equal(exportFilename('md', new Date('2026-11-04T10:00:00Z')), 'corpusil-answer-2026-11-04.md');
});
