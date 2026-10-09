const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');

// A rename must not log a desktop user out of the backend they configured.
// The saved address lived under an "aegis." localStorage key; changing the key
// without carrying the value over would leave the app silently pointed at
// localhost, on a machine where the real backend is somewhere else entirely,
// with nothing on screen to explain it.

function loadModule(storage, tauri = true) {
  const source = fs.readFileSync('lib/runtime-backend.ts', 'utf8');
  const scope = {
    exports: {},
    window: { localStorage: storage },
    process: { env: {} },
    // A fresh vm context has no Node globals, so without this `new URL(...)`
    // inside the module throws, every stored value looks invalid, and these
    // tests pass for the wrong reason.
    URL,
    require: (name) => (name === '@/lib/desktop' ? { isTauriDesktop: () => tauri } : require(name)),
  };
  scope.module = { exports: scope.exports };
  vm.runInNewContext(
    ts.transpileModule(source, {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
    }).outputText,
    scope,
  );
  return scope.module.exports;
}

function fakeStorage(initial = {}) {
  const data = { ...initial };
  return {
    data,
    getItem: (k) => (k in data ? data[k] : null),
    setItem: (k, v) => { data[k] = String(v); },
    removeItem: (k) => { delete data[k]; },
  };
}

const LEGACY = 'aegis.desktop.backend-base-url.v1';
const CURRENT = 'corpusil.desktop.backend-base-url.v1';
// Deliberately not called URL: that identifier is the global class the
// harness passes into the vm context.
const SAVED = 'https://corpusil-device.example.ts.net';
const LOCALHOST = 'http://localhost:8000';

test('a backend saved under the old name is still used after the rename', () => {
  const mod = loadModule(fakeStorage({ [LEGACY]: SAVED }));
  assert.equal(mod.getRuntimeBackendUrl(), SAVED);
});

test('the value moves to the new key and the old one is cleared', () => {
  const storage = fakeStorage({ [LEGACY]: SAVED });
  loadModule(storage).getRuntimeBackendUrl();
  assert.equal(storage.data[CURRENT], SAVED);
  assert.equal(LEGACY in storage.data, false, 'the old key was left behind');
});

test('a value already under the new key wins and the old one is untouched', () => {
  const current = 'https://new.example.ts.net';
  const storage = fakeStorage({ [LEGACY]: SAVED, [CURRENT]: current });
  const mod = loadModule(storage);
  assert.equal(mod.getRuntimeBackendUrl(), current);
  assert.equal(storage.data[LEGACY], SAVED);
});

test('an override saved under either key is reported as an override', () => {
  assert.equal(loadModule(fakeStorage({ [LEGACY]: SAVED })).hasRuntimeBackendOverride(), true);
  assert.equal(loadModule(fakeStorage({ [CURRENT]: SAVED })).hasRuntimeBackendOverride(), true);
  assert.equal(loadModule(fakeStorage({})).hasRuntimeBackendOverride(), false);
});

test('resetting clears both keys, so a reset is not undone by the migration', () => {
  const storage = fakeStorage({ [LEGACY]: SAVED, [CURRENT]: SAVED });
  loadModule(storage).resetRuntimeBackendUrl();
  assert.deepEqual(Object.keys(storage.data), []);
});

test('a stored value that is no longer valid is discarded, not migrated forward', () => {
  const storage = fakeStorage({ [LEGACY]: 'http://insecure.example.com' });
  const mod = loadModule(storage);
  assert.equal(mod.getRuntimeBackendUrl(), LOCALHOST);
  assert.equal(CURRENT in storage.data, false, 'an invalid address was kept under the new key');
});
