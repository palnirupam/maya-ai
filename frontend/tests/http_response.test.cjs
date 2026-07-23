const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const ts = require('typescript');

function loadHttpHelpers() {
  const sourcePath = path.join(__dirname, '..', 'src', 'services', 'http.ts');
  const source = fs.readFileSync(sourcePath, 'utf8');
  const output = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  const module = { exports: {} };
  const evaluate = new Function('exports', 'require', 'module', output);
  evaluate(module.exports, require, module);
  return module.exports;
}

const { requireOk } = loadHttpHelpers();

test('requireOk returns successful responses unchanged', async () => {
  const response = { ok: true };
  assert.equal(await requireOk(response, 'fallback'), response);
});

test('requireOk surfaces backend detail for non-2xx responses', async () => {
  const response = { ok: false, json: async () => ({ detail: 'Permission write failed' }) };
  await assert.rejects(requireOk(response, 'fallback'), /Permission write failed/);
});

test('requireOk uses its fallback when an error body is not JSON', async () => {
  const response = { ok: false, json: async () => { throw new Error('not json'); } };
  await assert.rejects(requireOk(response, 'Save failed'), /Save failed/);
});
