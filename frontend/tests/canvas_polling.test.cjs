const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const ts = require('typescript');

function loadCanvasPollingHelpers() {
  const sourcePath = path.join(__dirname, '..', 'src', 'services', 'canvasPolling.ts');
  const source = fs.readFileSync(sourcePath, 'utf8');
  const output = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  const module = { exports: {} };
  const evaluate = new Function('exports', 'require', 'module', output);
  evaluate(module.exports, require, module);
  return module.exports;
}

const { createCanvasPollTracker } = loadCanvasPollingHelpers();

test('canvas poll tracker ignores canvases older than the current app instance', () => {
  const tracker = createCanvasPollTracker(1_000_000);

  assert.equal(tracker.accept({ session_id: 'old', updated_at: 999 }), null);
  assert.equal(tracker.accept({ session_id: 'same-time', updated_at: 1000 }), null);
});

test('canvas poll tracker accepts only genuinely newer updates', () => {
  const tracker = createCanvasPollTracker(1_000_000);

  assert.equal(tracker.accept({ session_id: 'new', updated_at: 1000.25 }), 'new');
  assert.equal(tracker.accept({ session_id: 'duplicate', updated_at: 1000.25 }), null);
  assert.equal(tracker.accept({ session_id: 'newer', updated_at: 1001 }), 'newer');
});

test('canvas poll tracker rejects incomplete or invalid endpoint data', () => {
  const tracker = createCanvasPollTracker(1_000_000);

  assert.equal(tracker.accept({ session_id: null, updated_at: 1001 }), null);
  assert.equal(tracker.accept({ session_id: 'bad', updated_at: Number.NaN }), null);
});
