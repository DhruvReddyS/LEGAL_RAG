const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const loadTs = require('./load-ts.cjs');

const prefs = loadTs('lib/preferences.ts');
const help = loadTs('lib/human-help.ts');
const releases = loadTs('lib/release-manifest.ts');
const history = loadTs('lib/history-view.ts');
const site = loadTs('lib/site.ts');

test('preferences start from the browser data-saver setting', () => {
  assert.equal(prefs.parsePreferences(null, true).lowBandwidth, true);
  assert.equal(prefs.parsePreferences(null, false).lowBandwidth, false);
});

test('an explicit choice beats data-saver', () => {
  assert.equal(prefs.parsePreferences(JSON.stringify({ lowBandwidth: false }), true).lowBandwidth, false);
});

test('bad stored preferences fall back rather than break the page', () => {
  assert.equal(prefs.parsePreferences('{nonsense').textSize, 'standard');
  assert.equal(prefs.parsePreferences(JSON.stringify({ textSize: 'gigantic' })).textSize, 'standard');
});

test('text sizes scale up, never down', () => {
  assert.equal(prefs.scaleFor('standard'), 1);
  assert.ok(prefs.scaleFor('large') > 1);
  assert.ok(prefs.scaleFor('larger') > prefs.scaleFor('large'));
});

test('low-bandwidth mode asks for less', () => {
  const low = prefs.bandwidthPlan(true);
  const normal = prefs.bandwidthPlan(false);
  assert.ok(low.historyPageSize < normal.historyPageSize);
  assert.equal(low.pollCorpusStatus, false);
  assert.ok(low.pollIntervalMs > normal.pollIntervalMs);
});

test('applying preferences marks the root element', () => {
  const root = { dataset: {}, style: { setProperty(name, value) { this[name] = value; } } };
  prefs.applyPreferences({ textSize: 'larger', lowBandwidth: true }, root);
  assert.equal(root.dataset.textSize, 'larger');
  assert.equal(root.dataset.lowBandwidth, 'on');
  assert.equal(root.style['--reading-scale'], '1.3');
});

for (const role of ['citizen', 'police', 'advocate', 'admin', 'anything-else']) {
  test(`an abstention gives a ${role} a human route`, () => {
    const result = help.humanHelpRoutes(role);
    assert.ok(result.heading && result.lead);
    assert.ok(result.routes.length >= 2);
  });
}

test('a citizen is given legal aid, with the number dialable', () => {
  const { routes } = help.humanHelpRoutes('citizen');
  const aid = routes.find(route => route.phone);
  assert.equal(aid.phone, help.LEGAL_AID_HELPLINE);
  assert.ok(routes.some(route => /District Legal Services Authority/.test(route.title)));
  assert.ok(routes.some(route => /advocate/i.test(route.title)));
});

test('no route recommends a particular lawyer or promises an outcome', () => {
  for (const role of ['citizen', 'police', 'advocate']) {
    const text = JSON.stringify(help.humanHelpRoutes(role)).toLowerCase();
    assert.doesNotMatch(text, /\bwin\b|guarantee|best lawyer|top advocate|adv\. /);
  }
});

const SHA = 'a'.repeat(64);
const artifact = (name, over = {}) => ({ name, sha256: SHA, bytes: 1048576, url: `https://example.com/${name}`, ...over });

test('artifacts are sorted to the right platform', () => {
  assert.equal(releases.platformOf('Corpusil_0.4.0_aarch64.dmg'), 'macos');
  assert.equal(releases.platformOf('Corpusil_0.4.0_x64_en-US.msi'), 'windows');
  assert.equal(releases.platformOf('Corpusil-setup.exe'), 'windows');
  assert.equal(releases.platformOf('corpusil_0.4.0_amd64.AppImage'), 'linux');
  assert.equal(releases.platformOf('corpusil_0.4.0_amd64.deb'), 'linux');
  assert.equal(releases.platformOf('latest.json'), null);
  assert.equal(releases.platformOf('Corpusil.dmg.sig'), null);
});

test('a valid manifest parses and filters by platform', () => {
  const manifest = releases.parseManifest({ version: '0.4.0', published: '2026-11-04', artifacts: [artifact('a.dmg'), artifact('b.msi')] });
  assert.equal(releases.artifactsFor(manifest, 'macos').length, 1);
  assert.equal(releases.artifactsFor(manifest, 'linux').length, 0);
});

test('anything unverifiable is left out, not shown', () => {
  const manifest = releases.parseManifest({
    version: '0.4.0',
    artifacts: [
      artifact('good.dmg'),
      artifact('short.dmg', { sha256: 'abc' }),
      artifact('http.dmg', { url: 'http://example.com/x.dmg' }),
      artifact('script.dmg', { url: 'javascript:alert(1)' }),
      artifact('unknown.zip'),
    ],
  });
  assert.deepEqual([...manifest.artifacts.map(item => item.name)], ['good.dmg']);
});

test('no manifest, or nothing usable in one, is null so the page can say so', () => {
  assert.equal(releases.parseManifest(null), null);
  assert.equal(releases.parseManifest('text'), null);
  assert.equal(releases.parseManifest({ version: '1', artifacts: [] }), null);
  assert.equal(releases.parseManifest({ artifacts: [artifact('a.dmg')] }), null);
  assert.deepEqual(Array.from(releases.artifactsFor(null, 'macos')), []);
});

test('sizes read naturally', () => {
  assert.equal(releases.formatBytes(0), '');
  assert.equal(releases.formatBytes(52 * 1024 * 1024), '52 MB');
  assert.equal(releases.formatBytes(3 * 1024 * 1024 * 1024), '3.0 GB');
});

test('pages merge without repeats, and earlier entries win', () => {
  const merged = history.mergeById([{ id: 'a', pinned: true }], [{ id: 'a', pinned: false }, { id: 'b' }]);
  assert.deepEqual([...merged.map(item => item.id)], ['a', 'b']);
  assert.equal(merged[0].pinned, true);
});

test('a matter name is tidied, and blank clears it', () => {
  assert.equal(history.normalizeMatter('  Rent   dispute '), 'Rent dispute');
  assert.equal(history.normalizeMatter('   '), null);
  assert.equal(history.normalizeMatter('x'.repeat(200)).length, 120);
});

test('relative days', () => {
  const now = new Date('2026-11-04T12:00:00Z');
  assert.equal(history.formatRelativeDay('2026-11-04T01:00:00Z', now), 'Today');
  assert.equal(history.formatRelativeDay('2026-11-03T10:00:00Z', now), 'Yesterday');
  assert.equal(history.formatRelativeDay('2026-11-01T10:00:00Z', now), '3 days ago');
  assert.equal(history.formatRelativeDay('nonsense', now), '');
});

test('debounce fires once, with the last value, and can be cancelled', async () => {
  const seen = [];
  const wrapped = history.debounce(value => seen.push(value), 5);
  wrapped('a');
  wrapped('b');
  await new Promise(resolve => setTimeout(resolve, 20));
  assert.deepEqual(seen, ['b']);
  wrapped('c');
  wrapped.cancel();
  await new Promise(resolve => setTimeout(resolve, 20));
  assert.deepEqual(seen, ['b']);
});

test('every public page exists as a route and reaches the app through one constant', () => {
  for (const route of Object.values(site.SITE_ROUTES)) {
    assert.ok(fs.existsSync(`app${route}/page.tsx`), route);
  }
  const hardcoded = [];
  const walk = dir => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const path = `${dir}/${entry.name}`;
      if (entry.isDirectory()) walk(path);
      else if (/href="\/"/.test(fs.readFileSync(path, 'utf8'))) hardcoded.push(path);
    }
  };
  for (const route of Object.values(site.SITE_ROUTES)) walk(`app${route}`);
  walk('components/platform');
  assert.deepEqual(hardcoded, []);
});

test('the public copy does not overclaim', () => {
  const pages = [];
  const walk = dir => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const path = `${dir}/${entry.name}`;
      if (entry.isDirectory()) walk(path);
      else pages.push(fs.readFileSync(path, 'utf8'));
    }
  };
  for (const route of Object.values(site.SITE_ROUTES)) walk(`app${route}`);
  walk('components/platform');
  const text = pages.join('\n').toLowerCase();
  for (const banned of [
    'zero hallucination',
    'hallucination-free',
    'never wrong',
    'always accurate',
    '100% accurate',
    'guaranteed accurate',
    'replaces a lawyer',
    'instead of a lawyer',
    'ai lawyer',
    'dpdp compliant',
    'fully compliant',
  ]) {
    assert.ok(!text.includes(banned), banned);
  }
});

test('corpus figures add up', () => {
  const facts = site.CORPUS_FACTS;
  assert.equal(facts.central + facts.andhraPradesh + facts.telangana, facts.documents);
  assert.equal(facts.supremeCourtJudgments + facts.andhraHighCourtJudgments, facts.judgments);
});
