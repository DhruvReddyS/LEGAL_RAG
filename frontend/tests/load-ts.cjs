// Loads a lib/ module the way the app bundles it. Type imports vanish in the
// transpile, so a module with only type imports runs without its dependencies.
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');

module.exports = function loadTs(path, globals = {}) {
  const scope = { exports: {} };
  const source = ts.transpileModule(fs.readFileSync(path, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  vm.runInNewContext(source, {
    ...scope,
    module: scope,
    URL,
    TextDecoder,
    ReadableStream,
    setTimeout,
    clearTimeout,
    Promise,
    Error,
    JSON,
    Date,
    Math,
    Set,
    ...globals,
  });
  return scope.exports;
};
