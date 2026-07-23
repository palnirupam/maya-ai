'use strict';

function createIdempotencyStore({ ttlMs = 10 * 60_000, maxEntries = 1000 } = {}) {
    const entries = new Map();

    function prune(now = Date.now()) {
        for (const [key, entry] of entries) {
            if (now - entry.createdAt >= ttlMs) entries.delete(key);
        }
        while (entries.size > maxEntries) {
            entries.delete(entries.keys().next().value);
        }
    }

    function run(requestId, fingerprint, operation) {
        if (!requestId) return operation();

        prune();
        const existing = entries.get(requestId);
        if (existing) {
            if (existing.fingerprint !== fingerprint) {
                const error = new Error('requestId was already used for a different payload');
                error.code = 'IDEMPOTENCY_CONFLICT';
                return Promise.reject(error);
            }
            return existing.promise;
        }

        const promise = Promise.resolve().then(operation).catch(error => {
            const current = entries.get(requestId);
            if (current && current.promise === promise) entries.delete(requestId);
            throw error;
        });
        entries.set(requestId, { fingerprint, promise, createdAt: Date.now() });
        prune();
        return promise;
    }

    function get(requestId, fingerprint) {
        if (!requestId) return null;
        prune();
        const existing = entries.get(requestId);
        if (!existing) return null;
        if (existing.fingerprint !== fingerprint) {
            const error = new Error('requestId was already used for a different payload');
            error.code = 'IDEMPOTENCY_CONFLICT';
            throw error;
        }
        return existing.promise;
    }

    return { run, get, prune, size: () => entries.size };
}

module.exports = { createIdempotencyStore };
