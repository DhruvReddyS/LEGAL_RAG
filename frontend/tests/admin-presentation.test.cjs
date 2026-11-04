const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const vm = require('node:vm');

const moduleScope = { exports: {} };
vm.runInNewContext(
  ts.transpileModule(fs.readFileSync('lib/admin-presentation.ts', 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText,
  { ...moduleScope, Date, Math, Number, Object, Array, JSON, encodeURIComponent, String },
);
const p = moduleScope.exports;

test('an unfinished gate is neither a pass nor a failure', () => {
  assert.equal(p.gateTone('passed'), 'ok');
  assert.equal(p.gateTone('failed'), 'bad');
  assert.equal(p.gateTone('incomplete'), 'warn');
  assert.equal(p.gateTone('skipped'), 'warn');
  assert.equal(p.gateTone('not_run'), 'neutral');
  assert.equal(p.gateLabel('not_run'), 'Not run');
});

test('a document is shown as current only when the corpus says it is', () => {
  assert.equal(p.currencyTone('current'), 'ok');
  assert.equal(p.currencyTone('unverified'), 'warn');
  assert.equal(p.currencyTone('warned'), 'warn');
  assert.equal(p.currencyTone('repealed_or_superseded'), 'bad');
  assert.equal(p.currencyLabel('unverified'), 'Status unverified');
});

test('a cleared filter leaves the query entirely', () => {
  assert.equal(p.toQuery({}), '');
  assert.equal(p.toQuery({ q: '', role: undefined, status: null }), '');
  assert.equal(p.toQuery({ q: 'a&b', page: 2 }), '?q=a%26b&page=2');
});

test('paging reads correctly at the edges', () => {
  assert.deepEqual({ ...p.pageSpan(1, 25, 0) }, { first: 0, last: 0, pages: 1, hasPrevious: false, hasNext: false });
  assert.deepEqual({ ...p.pageSpan(1, 25, 26) }, { first: 1, last: 25, pages: 2, hasPrevious: false, hasNext: true });
  assert.deepEqual({ ...p.pageSpan(2, 25, 26) }, { first: 26, last: 26, pages: 2, hasPrevious: true, hasNext: false });
  assert.deepEqual({ ...p.pageSpan(1, 25, 25) }, { first: 1, last: 25, pages: 1, hasPrevious: false, hasNext: false });
});

test('a number nobody measured never reads as zero', () => {
  assert.equal(p.formatPercent(null), 'Not measured');
  assert.equal(p.formatPercent(0), '0.0%');
  assert.equal(p.formatCount(null), 'Not measured');
  assert.equal(p.formatCount(0), '0');
  assert.equal(p.formatDuration(null), 'Not measured');
  assert.equal(p.formatMetric(null), 'Not measured');
});

test('durations use a unit a person can read', () => {
  assert.equal(p.formatDuration(250), '250 ms');
  assert.equal(p.formatDuration(1500), '1.5 s');
  assert.equal(p.formatDuration(120000), '2.0 min');
});

test('approving over unfinished gates takes an override', () => {
  const clean = p.decisionRules({ all_passed: true, counts: { passed: 7 } }, false);
  assert.equal(clean.canApprove, true);
  assert.equal(clean.needsOverride, false);

  const failing = { all_passed: false, counts: { passed: 1, failed: 1, incomplete: 1, not_run: 4 } };
  assert.equal(p.decisionRules(failing, false).canApprove, false);
  assert.equal(p.decisionRules(failing, true).canApprove, true);
  assert.match(p.decisionRules(failing, false).summary, /1 failed, 5 not finished/);
});

test('a decision needs a real reason', () => {
  assert.equal(p.reasonIsSufficient('   short  '), false);
  assert.equal(p.reasonIsSufficient('Reviewed the retrieval analysis'), true);
});

test('the newest decision for a collection is the one that stands', () => {
  const decisions = [
    { collection: 'v5', decision: 'approve', decided_at: '2026-10-01T00:00:00Z' },
    { collection: 'v5', decision: 'refuse', decided_at: '2026-10-02T00:00:00Z' },
    { collection: 'v4', decision: 'approve', decided_at: '2026-10-03T00:00:00Z' },
  ];
  assert.equal(p.standingDecision(decisions, 'v5').decision, 'refuse');
  assert.equal(p.standingDecision(decisions, 'v9'), null);
});

test('a retention period is checked before it is sent', () => {
  assert.equal(p.retentionError('', 365), null, 'blank means keep everything');
  assert.equal(p.retentionError('400', 365), null);
  assert.match(p.retentionError('30', 365), /at least 365/);
  assert.match(p.retentionError('3.5', 7), /whole number/);
  assert.match(p.retentionError('-1', 7), /whole number/);
});

test('the purge total counts what goes and not what could not', () => {
  assert.equal(p.totalToPurge({ chat_history: 3, audit_logs: 2, closed_cases_failed: 9 }), 5);
});

test('a dry run stops being usable when it expires', () => {
  const now = new Date('2026-11-04T10:00:00Z');
  assert.equal(p.dryRunIsExpired('2026-11-04T09:59:59Z', now), true);
  assert.equal(p.dryRunIsExpired('2026-11-04T10:15:00Z', now), false);
});

test('a comparison reads as a change, or says there was none', () => {
  assert.equal(p.formatDelta(0), 'No change');
  assert.equal(p.formatDelta(0.0123), '+0.012');
  assert.equal(p.formatDelta(-2), '-2');
  assert.equal(p.formatDelta(null), '');
  assert.equal(p.metricLabel('recall_at_5'), 'Recall at 5');
  assert.equal(p.metricLabel('something_new'), 'something new');
});

test('audit metadata leaves nulls out and keeps structure compact', () => {
  const rows = [...p.metadataRows({ case_id: null, has_note: true, gates: { a: 'passed' } })].map(row => [...row]);
  assert.deepEqual(rows, [
    ['has note', 'true'],
    ['gates', '{"a":"passed"}'],
  ]);
});

const BOX = { width: 400, height: 200, left: 40, right: 10, top: 10, bottom: 30 };

test('a gap in the data is a gap in the line', () => {
  const chart = p.chartGeometry(
    [
      { label: 'a', value: 1 },
      { label: 'b', value: 2 },
      { label: 'c', value: null },
      { label: 'd', value: 3 },
      { label: 'e', value: 4 },
    ],
    BOX,
  );
  assert.equal(chart.segments.length, 2);
  assert.equal(chart.points[2].y, null);
  assert.equal(chart.hasData, true);
});

test('a lone point draws no line but stays placed for its marker', () => {
  const chart = p.chartGeometry([{ label: 'a', value: 1 }], BOX);
  assert.equal(chart.segments.length, 0);
  assert.equal(typeof chart.points[0].y, 'number');
  assert.equal(chart.points[0].x, BOX.left + (BOX.width - BOX.left - BOX.right) / 2);
});

test('a chart with nothing in it knows', () => {
  assert.equal(p.chartGeometry([], BOX).hasData, false);
  assert.equal(p.chartGeometry([{ label: 'a', value: null }], BOX).hasData, false);
});

test('values map inside the plot, zero on the baseline', () => {
  const chart = p.chartGeometry(
    [
      { label: 'a', value: 0 },
      { label: 'b', value: 1 },
    ],
    BOX,
    { max: 1 },
  );
  assert.equal(chart.points[0].y, BOX.height - BOX.bottom);
  assert.equal(chart.points[1].y, BOX.top);
  assert.equal(chart.ticks[0].value, 0);
  assert.equal(chart.ticks.at(-1).value, 1);
});

test('the axis rounds up to a readable number', () => {
  const chart = p.chartGeometry([{ label: 'a', value: 137 }, { label: 'b', value: 1 }], BOX);
  assert.equal(chart.ticks.at(-1).value, 200);
});

test('the crosshair snaps past a gap', () => {
  const placed = [
    { label: 'a', value: 1, x: 0, y: 5 },
    { label: 'b', value: null, x: 10, y: null },
    { label: 'c', value: 2, x: 20, y: 6 },
  ];
  assert.equal(p.nearestPoint(placed, 11).label, 'c');
  assert.equal(p.nearestPoint([], 11), null);
});

test('admin components follow the theme and use no colour literal', () => {
  const dir = path.join('components', 'admin');
  const sources = fs.readdirSync(dir).filter(name => name.endsWith('.tsx'));
  assert.ok(sources.length >= 8, 'the console components should be here');
  for (const name of sources) {
    const source = fs.readFileSync(path.join(dir, name), 'utf8');
    assert.equal(/#[0-9a-fA-F]{6}\b/.test(source), false, `${name} hardcodes a colour`);
    assert.equal(/\bbg-white\b/.test(source), false, `${name} paints bg-white`);
  }
  const css = fs.readFileSync(path.join('app', 'admin.css'), 'utf8');
  assert.equal(/#[0-9a-fA-F]{3,8}\b/.test(css), false, 'admin.css should use only tokens');
});

test('the admin stylesheet is loaded by the layout', () => {
  assert.match(fs.readFileSync(path.join('app', 'layout.tsx'), 'utf8'), /import ".\/admin.css"/);
});
