const test = require('node:test');
const assert = require('node:assert/strict');
const loadTs = require('./load-ts.cjs');
const {
  parseSse,
  viewFromEvent,
  viewFromJob,
  followJob,
  rememberActiveJob,
  readActiveJob,
  forgetActiveJob,
  EMPTY_VIEW,
} = loadTs('lib/job-stream.ts');

const encoder = new TextEncoder();

function streamOf(chunks, { hang = false } = {}) {
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      if (!hang) controller.close();
    },
  });
}

const response = (status, body) => ({ status, ok: status >= 200 && status < 300, body });
const running = (over = {}) => ({ id: 'j', status: 'running', progress: 10, result: null, stage_label: 'Searching', ...over });
const done = { id: 'j', status: 'succeeded', progress: 100, result: { answer: 'A' }, stage_label: null };

const stageEvent = (id, label, progress) =>
  `id: ${id}\nevent: stage\ndata: ${JSON.stringify({ progress, stage: 's', data: { label } })}\n\n`;
const END = 'event: end\ndata: {"reason":"finished"}\n\n';

function deps(over = {}) {
  return {
    openStream: async () => response(200, streamOf([END])),
    getJob: async () => done,
    sleep: async () => undefined,
    pollIntervalMs: 1,
    idleTimeoutMs: 50,
    maxStreamFailures: 3,
    maxPollFailures: 4,
    ...over,
  };
}

test('events are parsed across chunk boundaries, and a partial one waits', () => {
  const first = parseSse('id: 1\nevent: stage\ndata: {"a"');
  assert.deepEqual(Array.from(first.events), []);
  const second = parseSse(first.rest + ':1}\n\nid: 2\nevent: st');
  assert.equal(second.events.length, 1);
  assert.equal(second.events[0].id, 1);
  assert.equal(second.events[0].event, 'stage');
  assert.equal(second.events[0].data, '{"a":1}');
  assert.equal(second.rest, 'id: 2\nevent: st');
});

test('keep-alive comments are not events', () => {
  assert.equal(parseSse(': keep-alive\n\n').events.length, 0);
});

test('CRLF line endings parse the same', () => {
  const { events } = parseSse('id: 3\r\nevent: x\r\ndata: y\r\n\r\n');
  assert.equal(events[0].id, 3);
  assert.equal(events[0].data, 'y');
});

test('a stage event names the stage and moves progress', () => {
  const view = viewFromEvent(EMPTY_VIEW, { id: 1, event: 'stage', data: JSON.stringify({ progress: 40, data: { label: 'Checking' } }) });
  assert.equal(view.stageLabel, 'Checking');
  assert.equal(view.progress, 40);
});

test('located sources are carried, and rubbish changes nothing', () => {
  const view = viewFromEvent(EMPTY_VIEW, { id: 1, event: 'located_sources', data: JSON.stringify({ progress: 7, data: { sources: [{ title: 'x' }] } }) });
  assert.equal(view.locatedSources.length, 1);
  assert.equal(viewFromEvent(view, { id: 2, event: 'stage', data: 'not json' }), view);
});

test('a queue position comes from the job, and stages clear it', () => {
  const queued = viewFromJob(running({ status: 'queued', queue_position: 2, estimated_wait_seconds: 150 }));
  assert.equal(queued.queuePosition, 2);
  const started = viewFromEvent(queued, { id: 1, event: 'stage', data: JSON.stringify({ progress: 5, data: { label: 'x' } }) });
  assert.equal(started.queuePosition, null);
});

test('a job already finished returns without opening a stream', async () => {
  let opened = 0;
  const job = await followJob('j', deps({ openStream: async () => { opened += 1; return response(200, streamOf([])); } }));
  assert.equal(job.status, 'succeeded');
  assert.equal(opened, 0);
});

test('progress arrives over the stream and the result comes from the job', async () => {
  const seen = [];
  let polls = 0;
  const job = await followJob(
    'j',
    deps({
      openStream: async () => response(200, streamOf([stageEvent(1, 'Searching', 10), stageEvent(2, 'Checking', 60), END])),
      getJob: async () => (++polls === 1 ? running() : done),
    }),
    { onUpdate: view => seen.push(view.stageLabel) },
  );
  assert.equal(job.result.answer, 'A');
  assert.ok(seen.includes('Checking'));
  assert.equal(polls, 2);
});

test('a dropped connection resumes from the last event seen', async () => {
  const opened = [];
  let polls = 0;
  await followJob(
    'j',
    deps({
      openStream: async (_, last) => {
        opened.push(last);
        return opened.length === 1
          ? response(200, streamOf([stageEvent(7, 'Searching', 10)]))
          : response(200, streamOf([END]));
      },
      getJob: async () => (++polls >= 3 ? done : running()),
    }),
  );
  assert.deepEqual(opened, [0, 7]);
});

test('a stream cap falls back to polling and still finishes', async () => {
  let polls = 0;
  const job = await followJob(
    'j',
    deps({
      openStream: async () => response(429, null),
      getJob: async () => (++polls >= 3 ? done : running()),
    }),
  );
  assert.equal(job.status, 'succeeded');
  assert.ok(polls >= 3);
});

test('a stream that keeps failing falls back to polling', async () => {
  let opened = 0;
  let polls = 0;
  const job = await followJob(
    'j',
    deps({
      openStream: async () => { opened += 1; throw new TypeError('network'); },
      getJob: async () => (++polls >= 3 ? done : running()),
    }),
  );
  assert.equal(job.status, 'succeeded');
  assert.equal(opened, 3);
});

test('an expired session goes through the path that refreshes it, then reconnects', async () => {
  const statuses = [401, 200];
  let polls = 0;
  const job = await followJob(
    'j',
    deps({
      openStream: async () => response(statuses.shift(), streamOf([END])),
      getJob: async () => (++polls >= 4 ? done : running()),
    }),
  );
  assert.equal(job.status, 'succeeded');
  assert.equal(statuses.length, 0);
});

test('one failed poll does not end the wait (F19)', async () => {
  let polls = 0;
  const job = await followJob(
    'j',
    deps({
      openStream: async () => response(503, null),
      getJob: async () => {
        polls += 1;
        if (polls === 1) return running();
        if (polls === 2) throw new TypeError('network');
        return done;
      },
    }),
  );
  assert.equal(job.status, 'succeeded');
});

test('being denied is final, not retried', async () => {
  const denied = Object.assign(new Error('You do not own this job'), { status: 403 });
  await assert.rejects(
    followJob('j', deps({ getJob: async () => { throw denied; } })),
    /do not own/,
  );
});

test('polling eventually gives up on a dead server rather than spinning forever', async () => {
  let polls = 0;
  await assert.rejects(
    followJob('j', deps({
      openStream: async () => response(503, null),
      getJob: async () => { polls += 1; throw new TypeError('network'); },
    })),
    /network/,
  );
  assert.ok(polls >= 4);
});

test('a stream that goes silent is treated as dead', async () => {
  let polls = 0;
  let opened = 0;
  const job = await followJob(
    'j',
    deps({
      idleTimeoutMs: 5,
      openStream: async () => { opened += 1; return response(200, streamOf([], { hang: true })); },
      getJob: async () => (++polls >= 3 ? done : running()),
    }),
  );
  assert.equal(job.status, 'succeeded');
  assert.ok(opened >= 1);
});

test('stopping aborts', async () => {
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(followJob('j', deps(), { signal: controller.signal }), error => error.name === 'AbortError');
});

function memoryStore() {
  const data = new Map();
  return {
    data,
    getItem: key => (data.has(key) ? data.get(key) : null),
    setItem: (key, value) => data.set(key, value),
    removeItem: key => data.delete(key),
  };
}
const JOB_ID = '11111111-2222-3333-4444-555555555555';
const SESSION_ID = '66666666-7777-8888-9999-000000000000';

test('resuming remembers ids per user, and nothing a person typed', () => {
  const store = memoryStore();
  rememberActiveJob(store, 'user-a', { jobId: JOB_ID, sessionId: SESSION_ID, startedAt: 5, query: 'private' });
  const read = readActiveJob(store, 'user-a');
  assert.equal(read.jobId, JOB_ID);
  assert.equal(read.sessionId, SESSION_ID);
  assert.equal(readActiveJob(store, 'user-b'), null);
  forgetActiveJob(store, 'user-a');
  assert.equal(readActiveJob(store, 'user-a'), null);
});

test('a tampered or corrupt record is ignored', () => {
  const store = memoryStore();
  store.setItem('corpusil.active-job.v1:u', '{not json');
  assert.equal(readActiveJob(store, 'u'), null);
  store.setItem('corpusil.active-job.v1:u', JSON.stringify({ jobId: '../../admin', sessionId: SESSION_ID }));
  assert.equal(readActiveJob(store, 'u'), null);
});

test('storage being unavailable is not an error', () => {
  const broken = { getItem() { throw new Error('denied'); }, setItem() { throw new Error('denied'); }, removeItem() { throw new Error('denied'); } };
  rememberActiveJob(broken, 'u', { jobId: JOB_ID, sessionId: SESSION_ID, startedAt: 1 });
  forgetActiveJob(broken, 'u');
  assert.equal(readActiveJob(broken, 'u'), null);
});
