const test = require('node:test');
const assert = require('node:assert/strict');
const loadTs = require('./load-ts.cjs');
const { evidenceRejection, processEvidenceItem, queueSummary, MAX_EVIDENCE_BYTES, RATE_LIMIT_ATTEMPTS } = loadTs('lib/evidence-queue.ts');

const deps = (over = {}) => {
  const changes = [];
  return {
    changes,
    upload: async () => ({ id: 'object-1' }),
    index: async () => ({ pages: 2, chunks: 5 }),
    isRateLimited: error => error.status === 429,
    errorText: error => error.message,
    wait: async () => {},
    onChange: change => changes.push(change),
    ...over,
  };
};
const last = run => run.changes[run.changes.length - 1];

test('a file the server would refuse is refused before it is sent', () => {
  assert.equal(evidenceRejection({ size: 10, type: 'application/pdf' }), null);
  assert.equal(evidenceRejection({ size: 10, type: 'text/plain; charset=utf-8' }), null);
  assert.equal(evidenceRejection({ size: MAX_EVIDENCE_BYTES, type: 'text/plain' }), null);
  assert.match(evidenceRejection({ size: MAX_EVIDENCE_BYTES + 1, type: 'application/pdf' }), /25 MiB/);
  assert.match(evidenceRejection({ size: 0, type: 'application/pdf' }), /empty/);
  assert.match(evidenceRejection({ size: 10, type: 'application/x-msdownload' }), /PDF, TXT, PNG, JPEG and WebP/);
  assert.match(evidenceRejection({ size: 10, type: '' }), /PDF, TXT, PNG, JPEG and WebP/);
});

test('a file moves through upload and indexing to done', async () => {
  const run = deps();
  assert.equal(await processEvidenceItem({}, run), true);
  assert.deepEqual(run.changes.map(change => change.status).filter(Boolean), ['uploading', 'indexing', 'done']);
  assert.match(last(run).detail, /2 page\(s\), 5 private/);
});

test('a failed upload is reported on the row and does not throw', async () => {
  const run = deps({ upload: async () => { throw new Error('Too big'); } });
  assert.equal(await processEvidenceItem({}, run), false);
  assert.equal(last(run).status, 'failed');
  assert.equal(last(run).detail, 'Too big');
});

test('a file the server refused offers no retry, while a passing failure does', async () => {
  const refused = deps({ index: async () => { const e = new Error('Damaged'); e.status = 422; throw e; }, isRefusal: error => error.status === 422 });
  assert.equal(await processEvidenceItem({}, refused), false);
  assert.equal(last(refused).retryable, false);
  const outage = deps({ index: async () => { const e = new Error('Down'); e.status = 503; throw e; }, isRefusal: error => error.status === 422 });
  assert.equal(await processEvidenceItem({}, outage), false);
  assert.equal(last(outage).retryable, true);
});

test('a file the server refused is not described as stored, because it was not kept', async () => {
  const refused = deps({ index: async () => { const e = new Error('Damaged. The file was not kept.'); e.status = 422; throw e; }, isRefusal: error => error.status === 422 });
  assert.equal(await processEvidenceItem({}, refused), false);
  assert.equal(last(refused).detail, 'Damaged. The file was not kept.');
});

test('images the server reads by OCR are accepted, an executable still is not', () => {
  for (const type of ['image/png', 'image/jpeg', 'image/webp']) assert.equal(evidenceRejection({ size: 10, type }), null);
  assert.match(evidenceRejection({ size: 10, type: 'application/x-msdownload' }), /Only PDF, TXT, PNG, JPEG and WebP/);
});

test('a failed index says the file is stored, and a retry does not store it twice', async () => {
  let uploads = 0;
  const failing = deps({ upload: async () => { uploads += 1; return { id: 'object-9' }; }, index: async () => { throw new Error('No text'); } });
  assert.equal(await processEvidenceItem({}, failing), false);
  assert.match(last(failing).detail, /^Stored, but not indexed\. No text/);
  assert.equal(failing.changes.find(change => change.objectId).objectId, 'object-9');
  const seen = [];
  const retried = deps({ upload: async () => { uploads += 1; return { id: 'other' }; }, index: async id => { seen.push(id); return { pages: 1, chunks: 1 }; } });
  assert.equal(await processEvidenceItem({ objectId: 'object-9' }, retried), true);
  assert.equal(uploads, 1);
  assert.deepEqual(seen, ['object-9']);
});

test('the rate limit pauses the batch instead of failing the fifth file', async () => {
  let calls = 0;
  let waits = 0;
  const run = deps({
    wait: async () => { waits += 1; },
    index: async () => {
      calls += 1;
      if (calls < 3) throw Object.assign(new Error('Too many'), { status: 429 });
      return { pages: 1, chunks: 1 };
    },
  });
  assert.equal(await processEvidenceItem({}, run), true);
  assert.equal(waits, 2);
  assert.ok(run.changes.some(change => change.status === 'waiting'));
});

test('the wait is bounded', async () => {
  let calls = 0;
  const run = deps({ index: async () => { calls += 1; throw Object.assign(new Error('Too many'), { status: 429 }); } });
  assert.equal(await processEvidenceItem({}, run), false);
  assert.equal(calls, RATE_LIMIT_ATTEMPTS);
});

test('the summary counts failures as finished, so the bar completes', () => {
  const summary = queueSummary([{ status: 'done' }, { status: 'failed' }, { status: 'queued' }]);
  assert.equal(summary.finished, 2);
  assert.equal(summary.total, 3);
  assert.equal(summary.failed, 1);
  assert.equal(summary.active, true);
  assert.equal(queueSummary([{ status: 'done' }]).active, false);
});
