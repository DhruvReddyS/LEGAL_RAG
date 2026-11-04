// Loads a TypeScript module from frontend/ with its relative, "@/" and JSON
// imports, so a test runs the real code and not a copy of its logic.
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

const ROOT = path.resolve(__dirname, '..', '..');

function resolve(request, fromDir) {
  const base = request.startsWith('@/') ? path.join(ROOT, request.slice(2)) : path.resolve(fromDir, request);
  for (const candidate of [base, `${base}.ts`, `${base}.tsx`, `${base}.json`, path.join(base, 'index.ts')]) {
    if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) return candidate;
  }
  throw new Error(`Cannot resolve ${request} from ${fromDir}`);
}

function createLoader(stubs = {}) {
  const cache = new Map();
  function load(file) {
    if (cache.has(file)) return cache.get(file).exports;
    const moduleObject = { exports: {} };
    cache.set(file, moduleObject);
    if (file.endsWith('.json')) {
      moduleObject.exports = JSON.parse(fs.readFileSync(file, 'utf8'));
      return moduleObject.exports;
    }
    const { outputText } = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true, jsx: ts.JsxEmit.React },
    });
    const dir = path.dirname(file);
    const localRequire = request => {
      if (request in stubs) return stubs[request];
      if (request.startsWith('.') || request.startsWith('@/')) return load(resolve(request, dir));
      return require(request);
    };
    new Function('module', 'exports', 'require', outputText)(moduleObject, moduleObject.exports, localRequire);
    return moduleObject.exports;
  }
  return relative => load(resolve(relative.startsWith('@/') ? relative : `@/${relative}`, ROOT));
}

module.exports = { loadTs: createLoader(), createLoader, ROOT };
