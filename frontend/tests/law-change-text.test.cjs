const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const loadTs = require('./load-ts.cjs');

const { describeLawChange } = loadTs('lib/law-change-text.ts');

test('a replacement names its successor and date when the record has them', () => {
  assert.equal(
    describeLawChange({ current_status: 'superseded', superseded_by: 'The New Act', effective: '2030-01-01' }),
    'It has been replaced by The New Act, effective 2030-01-01.',
  );
});

test('a replacement with no recorded successor does not invent one', () => {
  assert.equal(
    describeLawChange({ current_status: 'superseded', superseded_by: null, effective: null }),
    'It is now recorded as replaced.',
  );
});

test('a correction says the earlier record was wrong', () => {
  assert.match(
    describeLawChange({ current_status: 'in_force', superseded_by: null, effective: null }),
    /has been corrected/,
  );
});

test('the account dialog shows the notice above its tabs', () => {
  const dialog = fs.readFileSync('components/platform/AccountDialog.tsx', 'utf8');
  assert.ok(dialog.indexOf('<LawChangeNotices />') < dialog.indexOf('className="acct-tabs"'));
  assert.ok(dialog.includes('<LawChangeNotices />'));
});
