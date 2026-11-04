const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');
const loadTs = require('./load-ts.cjs');

const SCRIPT = path.resolve('../scripts/generate_release_manifest.mjs');
const { parseManifest } = loadTs('lib/release-manifest.ts');

test('checksums come from the files, and the page accepts the result', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'corpusil-release-'));
  const output = path.join(dir, 'out', 'releases.json');
  fs.writeFileSync(path.join(dir, 'Corpusil_0.4.0_aarch64.dmg'), 'mac bytes');
  fs.writeFileSync(path.join(dir, 'Corpusil_0.4.0_x64.msi'), 'windows bytes');
  fs.writeFileSync(path.join(dir, 'latest.json'), '{}');
  fs.writeFileSync(path.join(dir, 'Corpusil.dmg.sig'), 'sig');

  const result = spawnSync('node', [SCRIPT, dir, '0.4.0', 'https://example.com/dl/', output], { encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr);

  const manifest = JSON.parse(fs.readFileSync(output, 'utf8'));
  assert.deepEqual(manifest.artifacts.map(item => item.name), ['Corpusil_0.4.0_aarch64.dmg', 'Corpusil_0.4.0_x64.msi']);
  const expected = crypto.createHash('sha256').update('mac bytes').digest('hex');
  assert.equal(manifest.artifacts[0].sha256, expected);
  assert.equal(manifest.artifacts[0].url, 'https://example.com/dl/Corpusil_0.4.0_aarch64.dmg');
  assert.equal(parseManifest(manifest).artifacts.length, 2);
});

test('an empty directory fails rather than publishing nothing', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'corpusil-release-'));
  const result = spawnSync('node', [SCRIPT, dir, '0.4.0', 'https://example.com/', path.join(dir, 'r.json')], { encoding: 'utf8' });
  assert.notEqual(result.status, 0);
  assert.equal(fs.existsSync(path.join(dir, 'r.json')), false);
});

test('a plain http download location is refused', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'corpusil-release-'));
  fs.writeFileSync(path.join(dir, 'a.dmg'), 'x');
  const result = spawnSync('node', [SCRIPT, dir, '0.4.0', 'http://example.com/', path.join(dir, 'r.json')], { encoding: 'utf8' });
  assert.notEqual(result.status, 0);
});
