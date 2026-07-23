import subprocess
from pathlib import Path


SERVICE_DIR = (
    Path(__file__).parents[1]
    / "tools"
    / "desktop"
    / "advanced"
    / "whatsapp_service"
)


def test_node_whatsapp_security_helpers():
    script = r"""
const assert = require('assert');
const { Readable } = require('stream');
const {
    validateApiKey, trustedOrigin, readJsonBody, assertString,
    assertSafeAttachment, maskPhone, safeAttachmentLabel, safeErrorLabel,
    MAX_BODY_BYTES,
} = require('./security');

(async () => {
    assert.throws(() => validateApiKey('default_maya_key_change_me'));
    assert.throws(() => validateApiKey('short'));
    assert.strictEqual(validateApiKey('x'.repeat(32)), 'x'.repeat(32));

    assert.strictEqual(trustedOrigin('http://127.0.0.1:5173'), 'http://127.0.0.1:5173');
    assert.strictEqual(trustedOrigin('http://localhost:3000'), 'http://localhost:3000');
    assert.strictEqual(trustedOrigin('https://evil.example'), null);
    assert.strictEqual(trustedOrigin('not a URL'), null);
    assert.strictEqual(maskPhone('919876543210@c.us'), '...3210');
    assert.strictEqual(maskPhone('1234'), '****');
    assert.strictEqual(maskPhone(''), '<unknown>');
    assert.strictEqual(safeAttachmentLabel('C:/private/reports/report.pdf'), 'report.pdf');
    assert.strictEqual(safeAttachmentLabel(''), '<unknown attachment>');
    assert.strictEqual(safeErrorLabel({ name: 'ConnectError', code: 'ECONNREFUSED' }),
        'ConnectError (ECONNREFUSED)');
    assert.strictEqual(safeErrorLabel({ name: 'Error', message: 'phone=919876543210' }),
        'Error');
    assert.strictEqual(safeErrorLabel({
        name: 'Phone919876543210Error', code: '919876543210'
    }), 'Error');

    assert.deepStrictEqual(await readJsonBody(Readable.from(['{"ok":true}'])), { ok: true });
    await assert.rejects(readJsonBody(Readable.from(['x'.repeat(MAX_BODY_BYTES + 1)])),
        error => error.statusCode === 413);
    await assert.rejects(readJsonBody(Readable.from(['{bad'])),
        error => error.statusCode === 400);

    assert.throws(() => assertString('x'.repeat(6), 'value', 5));
    assert.throws(() => assertSafeAttachment('C:/maya-ai/.env', {
        projectRoot: 'C:/maya-ai', dataDir: 'C:/maya-ai/data', homeDir: 'C:/Users/test'
    }), error => error.code === 'PROTECTED_ATTACHMENT');
    assert.throws(() => assertSafeAttachment('C:/Users/test/.ssh/id_rsa', {
        projectRoot: 'C:/maya-ai', dataDir: 'C:/maya-ai/data', homeDir: 'C:/Users/test'
    }));
    assert.strictEqual(
        assertSafeAttachment('C:/Users/test/Documents/report.pdf', {
            projectRoot: 'C:/maya-ai', dataDir: 'C:/maya-ai/data', homeDir: 'C:/Users/test'
        }),
        'C:\\Users\\test\\Documents\\report.pdf'
    );
    assert.strictEqual(
        assertSafeAttachment('C:/maya-ai/data/uploads/report.pdf', {
            projectRoot: 'C:/maya-ai', dataDir: 'C:/maya-ai/data', homeDir: 'C:/Users/test'
        }),
        'C:\\maya-ai\\data\\uploads\\report.pdf'
    );
})().catch(error => { console.error(error); process.exit(1); });
"""
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=SERVICE_DIR,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
