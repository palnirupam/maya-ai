import subprocess
from pathlib import Path


SERVICE_DIR = (
    Path(__file__).parents[1]
    / "tools"
    / "desktop"
    / "advanced"
    / "whatsapp_service"
)


def test_node_idempotency_store_deduplicates_and_rejects_conflicts():
    script = r"""
const assert = require('assert');
const { createIdempotencyStore } = require('./idempotency');

(async () => {
    const store = createIdempotencyStore({ ttlMs: 1000, maxEntries: 10 });
    let calls = 0;
    let release;
    const gate = new Promise(resolve => { release = resolve; });
    const operation = async () => { calls += 1; await gate; return { messageId: 'm1' }; };

    const first = store.run('request-1', 'same-payload', operation);
    const duplicate = store.run('request-1', 'same-payload', operation);
    await Promise.resolve();
    assert.strictEqual(calls, 1);
    assert.deepStrictEqual(await store.get('request-1', 'same-payload'), { messageId: 'm1' });
    release();
    assert.deepStrictEqual(await first, { messageId: 'm1' });
    assert.deepStrictEqual(await duplicate, { messageId: 'm1' });
    assert.deepStrictEqual(
        await store.run('request-1', 'same-payload', operation),
        { messageId: 'm1' }
    );
    assert.strictEqual(calls, 1);

    await assert.rejects(
        store.run('request-1', 'changed-payload', operation),
        error => error.code === 'IDEMPOTENCY_CONFLICT'
    );

    let attempts = 0;
    await assert.rejects(store.run('request-2', 'retryable', async () => {
        attempts += 1;
        throw new Error('temporary failure');
    }));
    assert.strictEqual(
        await store.run('request-2', 'retryable', async () => {
            attempts += 1;
            return 'recovered';
        }),
        'recovered'
    );
    assert.strictEqual(attempts, 2);
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
