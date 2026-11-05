const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const loadTs = require('./load-ts.cjs');
const docx = loadTs('lib/docx.ts', { TextEncoder, Uint8Array, Uint32Array, DataView, Number, String, Array });
const { buildDocx, documentXml, textToBlocks, htmlToBlocks, xmlText, crc32, docxFilename } = docx;

// Reads the file the way a word processor must: from the central directory.
function readZip(bytes) {
  const buffer = Buffer.from(bytes);
  const endAt = buffer.length - 22;
  assert.equal(buffer.readUInt32LE(endAt), 0x06054b50, 'end of central directory');
  const count = buffer.readUInt16LE(endAt + 10);
  let at = buffer.readUInt32LE(endAt + 16);
  const entries = new Map();
  const names = [];
  for (let i = 0; i < count; i += 1) {
    assert.equal(buffer.readUInt32LE(at), 0x02014b50, 'central header');
    assert.equal(buffer.readUInt16LE(at + 10), 0, 'stored');
    const crc = buffer.readUInt32LE(at + 16);
    const size = buffer.readUInt32LE(at + 24);
    const nameLength = buffer.readUInt16LE(at + 28);
    const local = buffer.readUInt32LE(at + 42);
    const name = buffer.toString('utf8', at + 46, at + 46 + nameLength);
    assert.equal(buffer.readUInt32LE(local), 0x04034b50, `local header of ${name}`);
    assert.equal(buffer.toString('utf8', local + 30, local + 30 + nameLength), name);
    const data = buffer.subarray(local + 30 + nameLength, local + 30 + nameLength + size);
    assert.equal(crc32(new Uint8Array(data)) >>> 0, crc, `crc of ${name}`);
    entries.set(name, data.toString('utf8'));
    names.push(name);
    at += 46 + nameLength;
  }
  return { entries, names };
}

// A small check that tags balance, which is what makes Word refuse a file outright.
function assertWellFormed(xml, label) {
  const stack = [];
  for (const match of xml.matchAll(/<(\/?)([\w:.-]+)((?:\s+[\w:.-]+="[^"<]*")*)\s*(\/?)>|<\?[^>]*\?>|([<>])/g)) {
    assert.equal(match[5], undefined, `${label}: stray ${match[5]} at ${match.index}`);
    if (!match[2]) continue;
    if (match[1]) assert.equal(stack.pop(), match[2], `${label}: closing ${match[2]}`);
    else if (!match[4]) stack.push(match[2]);
  }
  assert.deepEqual(stack, [], `${label}: unclosed`);
}

const SAMPLE = [
  { kind: 'heading', level: 1, text: 'Bail application' },
  { kind: 'paragraph', text: 'Plain & simple <text> with "quotes".' },
  { kind: 'bullet', text: 'A bullet' },
  { kind: 'number', n: 1, text: 'First' },
  { kind: 'number', n: 2, text: 'Second' },
  { kind: 'table', header: ['Exhibit', 'Place'], rows: [['A', 'Hyderabad'], ['B']] },
  { kind: 'paragraph', text: 'हिन्दी పరీక్ష' },
];

test('the package has the parts a word processor looks for, first the content types', () => {
  const { entries, names } = readZip(buildDocx(SAMPLE));
  assert.equal(names[0], '[Content_Types].xml');
  for (const part of ['_rels/.rels', 'word/document.xml', 'word/_rels/document.xml.rels', 'word/styles.xml', 'word/numbering.xml']) {
    assert.ok(entries.has(part), part);
  }
  assert.match(entries.get('[Content_Types].xml'), /PartName="\/word\/document\.xml"/);
  assert.match(entries.get('_rels/.rels'), /Target="word\/document\.xml"/);
  assert.match(entries.get('word/_rels/document.xml.rels'), /Target="numbering\.xml"/);
  for (const [name, xml] of entries) assertWellFormed(xml, name);
});

test('headings, paragraphs, lists and tables survive', () => {
  const { entries } = readZip(buildDocx(SAMPLE));
  const body = entries.get('word/document.xml');
  assert.match(body, /<w:pStyle w:val="Heading1"\/>.*Bail application/);
  assert.match(body, /<w:numId w:val="1"\/>.*A bullet/);
  assert.match(body, /<w:numId w:val="2"\/>.*First/);
  assert.match(body, /<w:numId w:val="2"\/>.*Second/);
  assert.match(body, /<w:tbl>.*<w:tblHeader\/>.*Exhibit.*Hyderabad.*<\/w:tbl>/);
  assert.ok(body.includes('हिन्दी పరీక్ష'), 'non-Latin text is kept');
  const styles = entries.get('word/styles.xml');
  assert.match(styles, /w:styleId="Heading1"/);
  assert.match(styles, /w:styleId="ListParagraph"/);
});

test('a short table row is padded, because Word needs the cells to match the grid', () => {
  const { xml } = documentXml([{ kind: 'table', header: ['A', 'B', 'C'], rows: [['1']] }]);
  const rows = xml.match(/<w:tr>.*?<\/w:tr>/g);
  assert.equal(rows.length, 2);
  for (const row of rows) assert.equal((row.match(/<w:tc>/g) || []).length, 3);
});

test('a draft number keeps its value after an interruption', () => {
  const { lists, xml } = documentXml([
    { kind: 'number', n: 1, text: 'a' },
    { kind: 'number', n: 2, text: 'b' },
    { kind: 'paragraph', text: 'interruption' },
    { kind: 'number', n: 3, text: 'c' },
    { kind: 'number', n: 1, text: 'fresh' },
  ]);
  assert.deepEqual([...lists].map(list => list.start), [1, 3, 1]);
  const { entries } = readZip(buildDocx([{ kind: 'number', n: 3, text: 'c' }]));
  assert.match(entries.get('word/numbering.xml'), /<w:num w:numId="2">.*<w:startOverride w:val="3"\/>/);
  assert.match(xml, /<w:numId w:val="4"\/>.*fresh/);
});

test('hostile text cannot become markup or break the file', () => {
  const hostile = 'a</w:t></w:r><w:r><w:t>b &amp; \u0000\u0001\u000B\uD800 <script>x</script>';
  const { entries } = readZip(buildDocx([{ kind: 'paragraph', text: hostile }]));
  const body = entries.get('word/document.xml');
  assertWellFormed(body, 'document');
  assert.ok(!body.includes('<script>'));
  assert.ok(body.includes('&lt;/w:t&gt;'));
  assert.ok(!/[\u0000-\u0008\u000B\u000C]/.test(body));
  assert.equal(xmlText('a😀b'), 'a😀b', 'a whole emoji is left alone');
});

test('draft text: capitals head a part, numbers list, the indent stays', () => {
  const blocks = textToBlocks([
    'FACTS AS INSTRUCTED',
    'The applicant was arrested on 3 May.',
    '',
    '1. First ground [1]',
    '2. Second ground',
    '- a dash item',
    '  (a) All documents:',
    '---',
    'Section 35(3) notice',
  ].join('\r\n'));
  assert.deepEqual(JSON.parse(JSON.stringify(blocks)), [
    { kind: 'heading', level: 2, text: 'FACTS AS INSTRUCTED' },
    { kind: 'paragraph', text: 'The applicant was arrested on 3 May.' },
    { kind: 'number', n: 1, text: 'First ground [1]' },
    { kind: 'number', n: 2, text: 'Second ground' },
    { kind: 'bullet', text: 'a dash item' },
    { kind: 'paragraph', text: '(a) All documents:', indent: 1 },
    { kind: 'paragraph', text: 'Section 35(3) notice' },
  ]);
});

test('a line of capitals with digits only is not mistaken for a heading unless it has letters', () => {
  const [digits] = textToBlocks('12/05/2026');
  assert.equal(digits.kind, 'paragraph');
  const [caption] = textToBlocks('IN THE COURT OF THE SESSIONS JUDGE, HYDERABAD');
  assert.equal(caption.kind, 'heading');
});

test('the case file HTML keeps its structure and none of its styling', () => {
  const html = `<!doctype html><html lang='en'><head><meta charset='utf-8'><title>Secret title: case file</title><style>body { color: red; }</style></head><body>
<h1>State v. A &amp; B</h1><p class='muted'>Compiled by <span class='state'>Officer</span>.</p><div class='note'>Not a filed document.</div>
<h2>1. Recorded facts</h2><dl><dt>Arrest</dt><dd>03 May 2026</dd></dl>
<h3>Exhibit &#x27;A&#x27;</h3><table><thead><tr><th scope="col">When</th><th scope="col">Who</th></tr></thead><tbody><tr><td>Today</td><td>&lt;script&gt;</td></tr></tbody></table>
<ul><li>One</li></ul><ol><li>Two</li><li>Three</li></ol>
<section class='draft'><h3>DRAFT: Notice, version 1</h3><pre>NOTICE
1. Appear on the date.
  (a) Bring papers &amp; ID.</pre></section></body></html>`;
  const blocks = JSON.parse(JSON.stringify(htmlToBlocks(html)));
  assert.deepEqual(blocks, [
    { kind: 'heading', level: 1, text: 'State v. A & B' },
    { kind: 'paragraph', text: 'Compiled by Officer.' },
    { kind: 'paragraph', text: 'Not a filed document.' },
    { kind: 'heading', level: 2, text: '1. Recorded facts' },
    { kind: 'paragraph', text: 'Arrest: 03 May 2026' },
    { kind: 'heading', level: 3, text: "Exhibit 'A'" },
    { kind: 'table', header: ['When', 'Who'], rows: [['Today', '<script>']] },
    { kind: 'bullet', text: 'One' },
    { kind: 'number', n: 1, text: 'Two' },
    { kind: 'number', n: 2, text: 'Three' },
    { kind: 'heading', level: 3, text: 'DRAFT: Notice, version 1' },
    { kind: 'heading', level: 2, text: 'NOTICE' },
    { kind: 'number', n: 1, text: 'Appear on the date.' },
    { kind: 'paragraph', text: '(a) Bring papers & ID.', indent: 1 },
  ]);
  const body = readZip(buildDocx(htmlToBlocks(html))).entries.get('word/document.xml');
  assertWellFormed(body, 'case file');
  assert.ok(!body.includes('color: red'));
  assert.ok(!body.includes('Secret title'));
});

test('filenames are safe', () => {
  assert.equal(docxFilename('Bail: application / regular', 2), 'bail-application-regular-v2.docx');
  assert.equal(docxFilename('!!!'), 'document.docx');
});

// macOS ships a reader written by someone else. It is not Word, but it is a real
// parser of this format, so run it where it exists.
test('an independent reader can open the file', { skip: process.platform !== 'darwin' }, () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'docx-'));
  try {
    const file = path.join(dir, 'sample.docx');
    fs.writeFileSync(file, Buffer.from(buildDocx(SAMPLE)));
    const text = execFileSync('/usr/bin/textutil', ['-convert', 'txt', '-stdout', file], { encoding: 'utf8' });
    for (const expected of ['Bail application', 'A bullet', 'First', 'Hyderabad', 'हिन्दी']) {
      assert.ok(text.includes(expected), `${expected} in ${text}`);
    }
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
