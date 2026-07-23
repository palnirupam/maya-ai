/**
 * Maya AI — WhatsApp Service (whatsapp-web.js)
 * Features: text messaging, single/multiple file sending, delivery confirmation.
 */

const { Client, LocalAuth, MessageMedia } = require('whatsapp-web.js');
const fs   = require('fs');
const path = require('path');
const http = require('http');
const crypto = require('crypto');
const { createIdempotencyStore } = require('./idempotency');
const {
    MAX_MESSAGE_LENGTH, MAX_CAPTION_LENGTH, MAX_BATCH_FILES,
    validateApiKey, trustedOrigin, readJsonBody, assertString, assertSafeAttachment,
    maskPhone, safeAttachmentLabel, safeErrorLabel,
} = require('./security');

// ── Rate Limiter State ────────────────────────────────────────────────────────
const authAttempts = new Map();
const WINDOW_MS = 60_000;

setInterval(() => {
    const now = Date.now();
    for (const [ip, record] of authAttempts.entries()) {
        if (now - record.first > WINDOW_MS) authAttempts.delete(ip);
    }
}, 10 * 60_000);

function checkAuthRateLimit(ip) {
    const now = Date.now();
    const record = authAttempts.get(ip) || { count: 0, first: now };
    if (now - record.first > WINDOW_MS) {
        authAttempts.set(ip, { count: 1, first: now });
        return true;
    }
    if (record.count >= 5) return false;
    record.count++;
    return true;
}

function safeCompare(a, b) {
    if (typeof a !== 'string' || typeof b !== 'string') return false;
    if (a.length !== b.length) return false;
    return crypto.timingSafeEqual(Buffer.from(a), Buffer.from(b));
}

// Map of messageId → { ack, timestamp } for delivery tracking
const sentMessageLog = {};
const sendRequests = createIdempotencyStore();

// whatsapp-web.js occasionally resolves client.sendMessage() to undefined, or to
// a message whose id has not hydrated yet, right after the 'ready' event — even
// though the message HAS already been submitted to WhatsApp. Return the serialized
// id when present, otherwise null. Callers MUST treat null as "sent, id
// unconfirmed" and never throw: throwing turned a delivered message into a false
// failure and (via the idempotency store's delete-on-throw) caused the client's
// retry to re-send, i.e. "sent 5-7 times but reported as failed".
function resolveSentMessageId(msg) {
    try {
        const id = msg && msg.id;
        if (!id) return null;
        if (typeof id._serialized === 'string' && id._serialized) return id._serialized;
        if (typeof id === 'string' && id) return id;
        return null;
    } catch (_) {
        return null;
    }
}

const PORT     = 9001;
const DATA_DIR = path.resolve(__dirname, '../../../../../data');
const AUTH_DIR = path.join(DATA_DIR, 'whatsapp_auth');
const PROJECT_ROOT = path.resolve(__dirname, '../../../../..');
const EXPECTED_API_KEY = validateApiKey(process.env.WA_API_KEY);

if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });
if (!fs.existsSync(AUTH_DIR)) fs.mkdirSync(AUTH_DIR, { recursive: true });

// ── State ─────────────────────────────────────────────────────────────────────
let client           = null;
let connectionStatus = 'disconnected';
let pendingPhone     = null;
let pairingResult    = null;
let intentionalStop  = false;   // true = we destroyed client on purpose, don't reconnect
let reconnectTimeout = null;

// ── Incoming Message State ────────────────────────────────────────────────────
const messageBuffers  = {};   // Map<chatId, Array<{from,name,body,ts}>> — circular, max BUFFER_MAX
const triggeredQueue  = [];   // Pending items waiting for Python to poll
const debounceTimers  = {};   // Map<chatId, timeoutHandle>
const knownSenders    = new Set();   // Approved phone numbers (no string after @c.us)
const blockedSenders  = new Set();   // Blocked phone numbers

const BUFFER_MAX   = 50;
const DEBOUNCE_MS  = parseInt(process.env.WA_DEBOUNCE_MS  || '1500', 10);
const CONTEXT_LIMIT = parseInt(process.env.WA_CONTEXT_LIMIT || '20',   10);
const MENTION_NAMES = (process.env.WA_MENTION_NAMES || 'Maya,AI').split(',').map(s => s.trim().toLowerCase());

function scheduleReconnect(ms = 5000) {
    if (intentionalStop) return;
    if (reconnectTimeout) clearTimeout(reconnectTimeout);
    reconnectTimeout = setTimeout(() => {
        reconnectTimeout = null;
        startClient(null);
    }, ms);
}

function cancelReconnect() {
    if (reconnectTimeout) { clearTimeout(reconnectTimeout); reconnectTimeout = null; }
}

// ── Create & start client ─────────────────────────────────────────────────────
async function startClient(pairingPhone) {
    // Cancel any pending auto-reconnect
    cancelReconnect();

    // Destroy existing client gracefully
    if (client) {
        intentionalStop = true;   // prevent the disconnected handler from triggering reconnect
        try { await client.destroy(); } catch (_) {}
        client = null;
        intentionalStop = false;
    }

    const c = new Client({
        authStrategy: new LocalAuth({ dataPath: AUTH_DIR }),
        puppeteer: {
            headless: true,
            args: [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--no-first-run'
            ]
        }
    });
    client = c;

    c.on('loading_screen', (percent, msg) => {
        if (percent % 25 === 0 || percent === 99) {
            console.log(`[WA] Loading ${percent}%.`);
        }
    });

    // When QR fires, request pairing code if phone is pending
    c.on('qr', async (_qr) => {
        if (pendingPhone) {
            const phone = pendingPhone;
            try {
                console.log(`[WA] Requesting pairing code for ${maskPhone(phone)}...`);
                const code = await c.requestPairingCode(phone);
                console.log('[WA] Pairing code generated successfully.');
                pairingResult = { code, error: null };
            } catch (err) {
                console.error('[WA] requestPairingCode failed:', safeErrorLabel(err));
                pairingResult = { code: null, error: err.message };
            }
        }
    });

    let authWatchdog = null;

    c.on('authenticated', () => {
        console.log('[WA] Authenticated!');
        connectionStatus = 'authenticated';
        pendingPhone = null;

        // Start watchdog: if not Ready within 60 seconds, assume hung and restart silently
        if (authWatchdog) clearTimeout(authWatchdog);
        authWatchdog = setTimeout(() => {
            console.error('[WA] Watchdog triggered: Stuck at loading screen for 60s. Restarting browser silently (No logout)...');
            if (client) {
                intentionalStop = true;
                try { client.destroy(); } catch (_) {}
                client = null;
                intentionalStop = false;
            }
            scheduleReconnect(2000);
        }, 60000);
    });

    c.on('auth_failure', (msg) => {
        console.error('[WA] Authentication failure reported.');
        connectionStatus = 'disconnected';
        if (authWatchdog) clearTimeout(authWatchdog);
        if (!intentionalStop) {
            try { fs.rmSync(AUTH_DIR, { recursive: true, force: true }); } catch (_) {}
            fs.mkdirSync(AUTH_DIR, { recursive: true });
            scheduleReconnect(5000);
        }
    });

    c.on('ready', () => {
        console.log('[WA] Ready! WhatsApp connected.');
        connectionStatus = 'connected';
        pendingPhone = null;
        if (authWatchdog) clearTimeout(authWatchdog);
    });

    // Track delivery status for sent messages (0=pending, 1=sent, 2=received, 3=read, 4=played)
    c.on('message_ack', (msg, ack) => {
        if (sentMessageLog[msg.id._serialized] !== undefined) {
            const statusMap = { 0: 'pending', 1: 'sent', 2: 'delivered', 3: 'read', 4: 'played' };
            sentMessageLog[msg.id._serialized] = statusMap[ack] || 'unknown';
            console.log(`[WA] Delivery update received: ${sentMessageLog[msg.id._serialized]}`);
        }
    });

    c.on('disconnected', (reason) => {
        console.log(`[WA] Disconnected. intentional=${intentionalStop}`);
        connectionStatus = 'disconnected';
        if (!intentionalStop) scheduleReconnect(5000);
    });

    // ── Incoming Message Listener ─────────────────────────────────────────────
    c.on('message', async (msg) => {
        // Hard ignores
        if (msg.fromMe) return;
        if (msg.isStatus) return;
        const chatId = msg.from;
        if (chatId === 'status@broadcast' || chatId.endsWith('@broadcast')) return;

        const isGroup = chatId.endsWith('@g.us');

        // Sender number (group messages have msg.author, DMs have msg.from)
        const rawSender = isGroup ? (msg.author || '') : chatId;
        let senderNumber = rawSender.replace(/@.*$/, '');

        // Skip blocked senders (early check)
        if (blockedSenders.has(senderNumber)) return;

        // Fetch sender name and real phone number
        let senderName = senderNumber;
        try {
            const contact = await msg.getContact();
            if (contact.number) senderNumber = contact.number.replace(/@.*$/, '');
            senderName = contact.name || contact.pushname || senderNumber;
        } catch (_) {}

        // Skip blocked senders (re-check with real number)
        if (blockedSenders.has(senderNumber)) return;

        // Fetch group name
        let groupName = null;
        if (isGroup) {
            try {
                const chat = await msg.getChat();
                groupName = chat.name || chatId;
            } catch (_) { groupName = chatId; }
        }

        // ── Buffer message ───────────────────────────────────────────────────
        if (!messageBuffers[chatId]) messageBuffers[chatId] = [];
        messageBuffers[chatId].push({ from: senderNumber, name: senderName, body: msg.body, ts: Date.now() });
        if (messageBuffers[chatId].length > BUFFER_MAX) messageBuffers[chatId].shift();

        // ── Decide whether to trigger notification ───────────────────────────
        let shouldTrigger = false;

        if (!isGroup) {
            // Private DM — always trigger
            shouldTrigger = true;
        } else {
            // Group — only trigger on mention or name match
            const myId = (c.info && c.info.wid) ? c.info.wid._serialized : null;
            const isMentioned = myId && (msg.mentionedIds || []).includes(myId);
            const bodyLower   = (msg.body || '').toLowerCase();
            const nameMatch   = MENTION_NAMES.some(n => bodyLower.includes(n));
            shouldTrigger = isMentioned || nameMatch;
        }

        if (!shouldTrigger) return;

        // ── Debounce ─────────────────────────────────────────────────────────
        if (debounceTimers[chatId]) clearTimeout(debounceTimers[chatId]);

        // Capture values for closure
        const capturedBody   = msg.body;
        const capturedNum    = senderNumber;
        const capturedName   = senderName;
        const capturedGroup  = groupName;
        const capturedIsGrp  = isGroup;
        const capturedKnown  = knownSenders.has(senderNumber);

        debounceTimers[chatId] = setTimeout(() => {
            delete debounceTimers[chatId];

            // Extract context (all buffered except the last/trigger message)
            const buf = messageBuffers[chatId] || [];
            const contextMessages = buf.slice(0, -1).slice(-CONTEXT_LIMIT);

            const uid = `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
            triggeredQueue.push({
                id: uid,
                chatId,
                isGroup: capturedIsGrp,
                groupName: capturedGroup,
                fromNumber: capturedNum,
                fromName: capturedName,
                triggerMsg: capturedBody,
                contextMessages,
                isKnown: capturedKnown,
                timestamp: Date.now()
            });
            console.log(`[WA-INCOMING] Queued message: isGroup=${capturedIsGrp} from=${maskPhone(capturedNum)}`);
        }, DEBOUNCE_MS);
    });

    console.log('[WA] Initializing Chrome + WhatsApp Web...');
    try {
        await c.initialize();
    } catch (err) {
        console.error('[WA] initialize() error:', safeErrorLabel(err));
        if (!intentionalStop) scheduleReconnect(8000);
    }
}

// Start on boot
startClient(null);

// ── HTTP Server ───────────────────────────────────────────────────────────────
const server = http.createServer(async (req, res) => {
    const allowedOrigin = trustedOrigin(req.headers.origin);
    if (allowedOrigin) res.setHeader('Access-Control-Allow-Origin', allowedOrigin);
    res.setHeader('Vary', 'Origin');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, x-api-key');
    if (req.method === 'OPTIONS') {
        if (req.headers.origin && !allowedOrigin) {
            res.writeHead(403); res.end(); return;
        }
        res.writeHead(204); res.end(); return;
    }

    // API Key Validation
    const clientIp = req.socket.remoteAddress || 'unknown';
    const providedKey = req.headers['x-api-key'] || '';
    
    if (!safeCompare(providedKey, EXPECTED_API_KEY)) {
        if (!checkAuthRateLimit(clientIp)) {
            res.writeHead(429, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: "Too many authentication failures" }));
            return;
        }
        res.writeHead(401, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: "Unauthorized" }));
        return;
    }

    let jsonBody = null;
    if (req.method === 'POST') {
        try {
            jsonBody = await readJsonBody(req);
        } catch (err) {
            if (!res.headersSent) {
                res.writeHead(err.statusCode || 400, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: err.message }));
            }
            return;
        }
    }

    async function ensureConnected() {
        // Only allow sending if fully 'connected' (Ready). 'authenticated' means it's still loading.
        if (connectionStatus === 'connected') return true;
        // If still initializing, wait briefly
        for (let i = 0; i < 10; i++) {
            await new Promise(r => setTimeout(r, 1000));
            if (connectionStatus === 'connected') return true;
        }
        return false;
    }

    // GET /status
    if (req.url === '/status' && req.method === 'GET') {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        let me = null;
        if (client && client.info && client.info.wid) {
            me = client.info.wid.user;
        }
        res.end(JSON.stringify({ status: connectionStatus, me: me }));
        return;
    }

    // GET /pair-code?phone=91XXXXXXXXXX
    if (req.url.startsWith('/pair-code') && req.method === 'GET') {
        try {
            const url = new URL(req.url, 'http://127.0.0.1');
            let phone = (url.searchParams.get('phone') || '').replace(/\D/g, '');
            if (phone.startsWith('00')) phone = phone.slice(2);
            else if (phone.startsWith('0')) phone = phone.slice(1);
            if (phone.length === 10) phone = '91' + phone;

            if (!phone || phone.length < 10) {
                res.writeHead(400);
                res.end(JSON.stringify({ error: 'Invalid phone number' }));
                return;
            }

            console.log(`\n[WA] === PAIRING REQUEST for ${maskPhone(phone)} ===`);

            // Clean auth to force fresh QR → pairing code flow
            try { fs.rmSync(AUTH_DIR, { recursive: true, force: true }); } catch (_) {}
            fs.mkdirSync(AUTH_DIR, { recursive: true });

            pendingPhone = phone;
            pairingResult = null;

            // Restart client fresh (will see no auth → emit QR → we intercept with pairing code)
            await startClient(phone);

            // Poll up to 60s for the code
            const deadline = Date.now() + 60000;
            while (Date.now() < deadline) {
                await new Promise(r => setTimeout(r, 500));
                if (pairingResult !== null) {
                    const { code, error } = pairingResult;
                    pairingResult = null;
                    if (code) {
                        res.writeHead(200, { 'Content-Type': 'application/json' });
                        res.end(JSON.stringify({ success: true, code }));
                    } else {
                        res.writeHead(500, { 'Content-Type': 'application/json' });
                        res.end(JSON.stringify({ error }));
                    }
                    return;
                }
            }
            res.writeHead(504, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: 'Timeout — try again.' }));

        } catch (err) {
            res.writeHead(500, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: err.message }));
        }
        return;
    }

    // POST /send
    if (req.url === '/send' && req.method === 'POST') {
        try {
                const { to, message, requestId } = jsonBody;
                assertString(to, 'to', 32);
                assertString(message, 'message', MAX_MESSAGE_LENGTH);
                let num = to.replace(/\D/g, '');
                if (num.startsWith('00')) num = num.slice(2);
                else if (num.startsWith('0')) num = num.slice(1);
                if (num.length === 10) num = '91' + num;
                const fingerprint = crypto.createHash('sha256')
                    .update(JSON.stringify({ type: 'text', to: num, message }))
                    .digest('hex');
                const cached = sendRequests.get(requestId, fingerprint);
                if (cached) {
                    const sendResult = await cached;
                    res.writeHead(200, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({
                        success: true,
                        messageId: sendResult.messageId,
                        status: sentMessageLog[sendResult.messageId] || 'sent',
                        deduplicated: true,
                    }));
                    return;
                }
                if (!(await ensureConnected())) {
                    res.writeHead(400, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ error: `Not connected (status: ${connectionStatus})` }));
                    return;
                }
                const chatId = `${num}@c.us`;
                console.log(`[WA] Checking registration for ${maskPhone(num)}...`);
                const isRegistered = await client.isRegisteredUser(chatId);
                if (!isRegistered) {
                    console.log(`[WA] Recipient ${maskPhone(num)} is not registered.`);
                    res.writeHead(400, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ error: `The number ${num} is not registered on WhatsApp.` }));
                    return;
                }

                console.log(`[WA] Sending to ${maskPhone(num)}.`);
                const sendResult = await sendRequests.run(requestId, fingerprint, async () => {
                    const msg = await client.sendMessage(chatId, message);
                    // whatsapp-web.js can resolve sendMessage() to undefined (or a
                    // message without a hydrated id) right after 'ready' even though
                    // the message HAS been submitted. Reading msg.id._serialized then
                    // threw, which (1) reported a false failure for a delivered
                    // message and (2) deleted the idempotency entry so the client's
                    // retry re-sent it — the "sent 5-7 times but says it failed" bug.
                    // Never throw here: the send already left the machine.
                    const messageId = resolveSentMessageId(msg);
                    if (messageId) sentMessageLog[messageId] = 'sent';
                    return { messageId };
                });
                console.log(`[WA] Sent OK to ${maskPhone(num)}.`);

                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({
                    success: true,
                    messageId: sendResult.messageId,
                    status: sentMessageLog[sendResult.messageId] || 'sent',
                }));
            } catch (err) {
                console.error('[WA] Send error:', safeErrorLabel(err));
                res.writeHead(err.statusCode || 500, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: err.message }));
            }
        return;
    }


    // ── Helper: normalize phone number ────────────────────────────────────────
    function normalizePhone(raw) {
        assertString(raw, 'phone number', 32);
        let num = raw.replace(/\D/g, '');
        if (num.startsWith('00')) num = num.slice(2);
        else if (num.startsWith('0')) num = num.slice(1);
        if (num.length === 10) num = '91' + num;
        if (num.length < 10 || num.length > 15) throw new Error('Invalid phone number');
        return num;
    }

    // POST /send-file  { to, filePath, caption? }
    if (req.url === '/send-file' && req.method === 'POST') {
        try {
                const { to, filePath, caption = '', requestId } = jsonBody;
                assertString(caption, 'caption', MAX_CAPTION_LENGTH, { optional: true });
                const absPath = assertSafeAttachment(filePath, {
                    projectRoot: PROJECT_ROOT, dataDir: DATA_DIR,
                });
                const num = normalizePhone(to);
                const fingerprint = crypto.createHash('sha256')
                    .update(JSON.stringify({ type: 'file', to: num, filePath: absPath, caption }))
                    .digest('hex');
                const cached = sendRequests.get(requestId, fingerprint);
                if (cached) {
                    const sendResult = await cached;
                    res.writeHead(200, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ success: true, messageId: sendResult.messageId, deduplicated: true }));
                    return;
                }
                if (!(await ensureConnected())) {
                    res.writeHead(400, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ error: `Not connected (status: ${connectionStatus})` }));
                    return;
                }
                if (!fs.existsSync(absPath)) {
                    res.writeHead(400, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ error: `File not found: ${absPath}` }));
                    return;
                }
                const chatId = `${num}@c.us`;
                const isRegistered = await client.isRegisteredUser(chatId);
                if (!isRegistered) {
                    res.writeHead(400, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ error: `Number ${num} is not registered on WhatsApp.` }));
                    return;
                }
                console.log(`[WA] Sending file "${safeAttachmentLabel(absPath)}" to ${maskPhone(num)}.`);
                const sendResult = await sendRequests.run(requestId, fingerprint, async () => {
                    const media = MessageMedia.fromFilePath(absPath);
                    const msg = await client.sendMessage(chatId, media, { caption });
                    // See /send: never throw after the send has left the machine, or
                    // a delivered attachment is reported failed and re-sent on retry.
                    const messageId = resolveSentMessageId(msg);
                    if (messageId) sentMessageLog[messageId] = 'sent';
                    return { messageId };
                });
                const msgId = sendResult.messageId;
                console.log('[WA] File sent OK.');
                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ success: true, messageId: msgId }));
            } catch (err) {
                console.error('[WA] send-file error:', safeErrorLabel(err));
                res.writeHead(err.statusCode || 500, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: err.message }));
            }
        return;
    }

    // POST /send-files  { to, files: [{ filePath, caption? }] }
    if (req.url === '/send-files' && req.method === 'POST') {
        try {
                const { to, files, requestId } = jsonBody;
                if (!Array.isArray(files) || files.length === 0 || files.length > MAX_BATCH_FILES) {
                    throw new Error(`files must contain 1-${MAX_BATCH_FILES} attachments`);
                }
                const num = normalizePhone(to);
                const normalizedFiles = files.map(item => ({
                    filePath: assertSafeAttachment(item && item.filePath, {
                        projectRoot: PROJECT_ROOT, dataDir: DATA_DIR,
                    }),
                    caption: assertString(item && item.caption, 'caption', MAX_CAPTION_LENGTH, { optional: true })
                }));
                const uniquePaths = new Set(normalizedFiles.map(item => item.filePath));
                if (uniquePaths.size !== normalizedFiles.length) {
                    const error = new Error('Duplicate attachment paths are not allowed');
                    error.statusCode = 400;
                    throw error;
                }
                const fingerprint = crypto.createHash('sha256')
                    .update(JSON.stringify({ type: 'files', to: num, files: normalizedFiles }))
                    .digest('hex');
                const cached = sendRequests.get(requestId, fingerprint);
                if (cached) {
                    const results = await cached;
                    res.writeHead(200, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ success: true, results, deduplicated: true }));
                    return;
                }
                if (!(await ensureConnected())) {
                    res.writeHead(400, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ error: `Not connected (status: ${connectionStatus})` }));
                    return;
                }
                const chatId = `${num}@c.us`;
                const isRegistered = await client.isRegisteredUser(chatId);
                if (!isRegistered) {
                    res.writeHead(400, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ error: `Number ${num} is not registered on WhatsApp.` }));
                    return;
                }
                const results = await sendRequests.run(requestId, fingerprint, async () => {
                    const sendResults = [];
                    for (const item of normalizedFiles) {
                    const absPath = item.filePath;
                    const caption = item.caption;
                    if (!fs.existsSync(absPath)) {
                        sendResults.push({ file: item.filePath, success: false, error: 'File not found' });
                        continue;
                    }
                    try {
                        console.log(`[WA] Sending file "${safeAttachmentLabel(absPath)}" to ${maskPhone(num)}.`);
                        const media = MessageMedia.fromFilePath(absPath);
                        const msg   = await client.sendMessage(chatId, media, { caption });
                        // See /send: a missing id means sent-but-unconfirmed, not
                        // failed. Throwing here would fail a delivered file and, on
                        // batch retry, re-send every file in the batch.
                        const msgId = resolveSentMessageId(msg);
                        if (msgId) sentMessageLog[msgId] = 'sent';
                        sendResults.push({ file: item.filePath, success: true, messageId: msgId });
                        console.log('[WA] File sent OK.');
                    } catch (fileErr) {
                        sendResults.push({ file: item.filePath, success: false, error: fileErr.message });
                    }
                    // 600ms delay between files to avoid WhatsApp rate-limiting
                    await new Promise(r => setTimeout(r, 600));
                    }
                    return sendResults;
                });
                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ success: true, results }));
            } catch (err) {
                console.error('[WA] send-files error:', safeErrorLabel(err));
                res.writeHead(err.statusCode || 500, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: err.message }));
            }
        return;
    }

    // GET /message-status?messageId=XXX
    if (req.url.startsWith('/message-status') && req.method === 'GET') {
        try {
            const url       = new URL(req.url, 'http://127.0.0.1');
            const messageId = url.searchParams.get('messageId') || '';
            if (!messageId) {
                res.writeHead(400, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: 'Missing messageId param' }));
                return;
            }
            const status = sentMessageLog[messageId] || 'unknown';
            console.log(`[WA] Message status check: ${status}`);
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ messageId, status }));
        } catch (err) {
            res.writeHead(500, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: err.message }));
        }
        return;
    }

    // ── GET /resolve-contact?name=Anup%20Kundu ────────────────────────────────────
    // Fuzzy-searches WhatsApp synced contacts by name/pushname and returns
    // ranked matches. Partial names and minor typos still match.
    if (req.url.startsWith('/resolve-contact') && req.method === 'GET') {
        try {
            if (!(await ensureConnected())) {
                res.writeHead(503, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: `Not connected (status: ${connectionStatus})` }));
                return;
            }
            const url  = new URL(req.url, 'http://127.0.0.1');
            const name = (url.searchParams.get('name') || '').trim();
            if (!name || name.length > 100) {
                res.writeHead(400, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: 'Invalid name parameter' }));
                return;
            }

            // Small bounded edit distance for typo tolerance
            function editDistance(a, b) {
                if (Math.abs(a.length - b.length) > 2) return 3;
                const dp = Array.from({ length: a.length + 1 }, (_, i) => [i]);
                for (let j = 1; j <= b.length; j++) dp[0][j] = j;
                for (let i = 1; i <= a.length; i++) {
                    for (let j = 1; j <= b.length; j++) {
                        dp[i][j] = Math.min(
                            dp[i - 1][j] + 1,
                            dp[i][j - 1] + 1,
                            dp[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1)
                        );
                    }
                }
                return dp[a.length][b.length];
            }

            const queryWords = name.toLowerCase()
                .replace(/[^\p{L}\p{N}\s]/gu, ' ')
                .split(/\s+/)
                .filter(w => w.length >= 2);

            const contacts = await client.getContacts();
            const scored = [];
            for (const c of contacts) {
                if (!c.isMyContact && !c.name) continue;   // skip random chat participants
                // Only real phone contacts — @lid entries carry internal ids
                // (e.g. 214396479496306) that are not dialable numbers.
                if (c.id?.server && c.id.server !== 'c.us') continue;
                const number = (c.number || '').replace(/\D/g, '');
                // Sanity: real phone numbers are 8-13 digits after normalization
                if (!number || number.length < 8 || number.length > 13) continue;
                // Country code +1 (US/Canada) numbers are exactly 11 digits —
                // longer ones are WhatsApp internal LID ids leaking through
                // (e.g. 1404521418771).
                if (number.startsWith('1') && number.length !== 11) continue;

                const displayName = c.name || c.pushname || c.shortName || '';
                if (!displayName) continue;
                const hayWords = displayName.toLowerCase()
                    .replace(/[^\p{L}\p{N}\s]/gu, ' ')
                    .split(/\s+/)
                    .filter(w => w.length >= 2);
                if (!hayWords.length) continue;

                let score = 0;
                for (const qw of queryWords) {
                    let best = 0;
                    for (const hw of hayWords) {
                        if (hw === qw) best = Math.max(best, 3);
                        else if (hw.startsWith(qw) || qw.startsWith(hw)) best = Math.max(best, 2);
                        else if (qw.length > 3 && editDistance(qw, hw) <= 1) best = Math.max(best, 1);
                    }
                    score += best;
                }
                if (score <= 0) continue;
                scored.push({ number, name: displayName, score });
            }

            scored.sort((a, b) => b.score - a.score);
            // Dedupe by number (same contact can appear twice in sync data)
            const seenNumbers = new Set();
            let deduped = scored.filter(m => {
                if (seenNumbers.has(m.number)) return false;
                seenNumbers.add(m.number);
                return true;
            });
            // Dedupe by identical display name too — WhatsApp's LID migration
            // creates ghost duplicates of the same contact with a different
            // "number". Keep the entry whose number shares the user's own
            // country prefix (most plausible real number).
            const myPrefix = (client.info?.wid?.user || '').slice(0, 2);
            const byName = new Map();
            for (const m of deduped) {
                const k = m.name.toLowerCase().trim();
                const prev = byName.get(k);
                if (!prev) { byName.set(k, m); continue; }
                const plaus = x => (myPrefix && x.number.startsWith(myPrefix) ? 2 : 0)
                                 + (x.number.length === 12 ? 1 : 0);
                if (plaus(m) > plaus(prev)) byName.set(k, m);
            }
            deduped = [...byName.values()].sort((a, b) => b.score - a.score);
            // Drop weak candidates when a clearly better match exists,
            // so a single obvious hit doesn't trigger disambiguation.
            const cutoff = deduped.length ? deduped[0].score * 0.7 : 0;
            const matches = deduped.filter(m => m.score >= cutoff).slice(0, 5);

            if (!matches.length) {
                res.writeHead(404, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: `Contact matching '${name}' not found in WhatsApp.` }));
                return;
            }

            const best = matches[0];
            console.log(`[WA] Contact resolution returned ${matches.length} candidate(s).`);
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({
                success: true,
                name: best.name,
                number: best.number,
                candidates: matches.map(m => ({ name: m.name, number: m.number, score: m.score })),
            }));
        } catch (err) {
            console.error('[WA] resolve-contact error:', safeErrorLabel(err));
            res.writeHead(500, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: err.message }));
        }
        return;
    }

    // ── GET /fetch-messages?phone=XXX&limit=10 ─────────────────────────────────────
    if (req.url.startsWith('/fetch-messages') && req.method === 'GET') {
        try {
            if (!(await ensureConnected())) {
                res.writeHead(503, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: `Not connected (status: ${connectionStatus})` }));
                return;
            }
            const url = new URL(req.url, 'http://127.0.0.1');
            const raw = url.searchParams.get('phone');
            if (!raw || typeof raw !== 'string' || raw.length > 20) {
                res.writeHead(400, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: "Invalid phone parameter" }));
                return;
            }
            const num = normalizePhone(raw);
            const chatId = `${num}@c.us`; // Currently restricted to individuals

            const limitParam = url.searchParams.get('limit');
            const parsedLimit = Math.min(parseInt(limitParam) || 10, 50);

            let chat;
            try {
                chat = await client.getChatById(chatId);
            } catch (_) {
                res.writeHead(404, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: "Chat not found or number not on WhatsApp" }));
                return;
            }

            const rawMessages = await chat.fetchMessages({ limit: parsedLimit });
            const messages = [];
            for (const msg of rawMessages) {
                let senderName = msg.fromMe ? 'Me' : num;
                if (!msg.fromMe) {
                    try {
                        const contact = await msg.getContact();
                        senderName = contact.pushname || contact.name || num;
                    } catch (_) {}
                }
                messages.push({
                    id: msg.id._serialized,
                    body: msg.body,
                    fromMe: msg.fromMe,
                    senderName: senderName,
                    timestampISO: new Date(msg.timestamp * 1000).toISOString(),
                    type: msg.type
                });
            }

            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ success: true, data: messages }));
        } catch (err) {
            console.error('[WA fetch-messages] Internal error:', safeErrorLabel(err));
            res.writeHead(500, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: "Internal server error" }));
        }
        return;
    }

    // ── GET /poll-triggered ───────────────────────────────────────────────────
    // Python polls this every 2s to get pending incoming messages.
    if (req.url === '/poll-triggered' && req.method === 'GET') {
        const items = triggeredQueue.splice(0);   // drain queue atomically
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ items }));
        return;
    }

    // ── POST /reply  { chatId, message } ─────────────────────────────────────
    // Group-safe reply — accepts full chatId (xxx@g.us or xxx@c.us).
    if (req.url === '/reply' && req.method === 'POST') {
        try {
                const { chatId: toChatId, message } = jsonBody;
                assertString(toChatId, 'chatId', 128, { pattern: /^\d+@(c|g)\.us$/ });
                assertString(message, 'message', MAX_MESSAGE_LENGTH);
                if (!(await ensureConnected())) {
                    res.writeHead(400, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ error: `Not connected (status: ${connectionStatus})` }));
                    return;
                }
                console.log(`[WA-INCOMING] Sending reply to ${maskPhone(toChatId)}.`);
                await client.sendMessage(toChatId, message);
                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ success: true }));
            } catch (err) {
                console.error('[WA-INCOMING] Reply error:', safeErrorLabel(err));
                res.writeHead(err.statusCode || 500, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: err.message }));
            }
        return;
    }

    // ── POST /register-known  { number } ─────────────────────────────────────
    if (req.url === '/register-known' && req.method === 'POST') {
        try {
            const number = normalizePhone(jsonBody.number);
            knownSenders.add(number);
            console.log(`[WA-INCOMING] Registered known sender: ${maskPhone(number)}`);
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ success: true }));
        } catch (e) { res.writeHead(400); res.end(JSON.stringify({ error: e.message })); }
        return;
    }

    // ── POST /block-number  { number } ───────────────────────────────────────
    if (req.url === '/block-number' && req.method === 'POST') {
        try {
            const number = normalizePhone(jsonBody.number);
            blockedSenders.add(number);
            knownSenders.delete(number);
            console.log(`[WA-INCOMING] Blocked sender: ${maskPhone(number)}`);
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ success: true }));
        } catch (e) { res.writeHead(400); res.end(JSON.stringify({ error: e.message })); }
        return;
    }

    // ── POST /revoke  { toChatId, count } ─────────────────────────────────────
    if (req.url === '/revoke' && req.method === 'POST') {
        try {
                const { toChatId, count } = jsonBody;
                assertString(toChatId, 'toChatId', 128, { pattern: /^\d+@(c|g)\.us$/ });
                if (count !== undefined && (!Number.isInteger(count) || count < 1 || count > 50)) {
                    throw new Error('count must be an integer between 1 and 50');
                }
                if (!(await ensureConnected())) {
                    res.writeHead(400, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ error: `Not connected` }));
                    return;
                }
                console.log(`[WA] Fetching messages for ${maskPhone(toChatId)} to revoke...`);
                const chat = await client.getChatById(toChatId);
                const messages = await chat.fetchMessages({ limit: 50 });
                let revoked = 0;
                const failures = [];
                const targetCount = count || 1;
                for (let i = messages.length - 1; i >= 0; i--) {
                    if (messages[i].fromMe) {
                        try {
                            await messages[i].delete(true); // true = delete for everyone
                            revoked++;
                        } catch (deleteErr) {
                            failures.push(safeErrorLabel(deleteErr));
                        }
                        if (revoked >= targetCount) break;
                        await new Promise(r => setTimeout(r, 800));
                    }
                }
                if (revoked === 0) {
                    res.writeHead(409, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({
                        success: false,
                        revoked: 0,
                        error: failures.length
                            ? 'WhatsApp rejected delete-for-everyone for the eligible sent messages'
                            : 'No eligible sent messages were found for delete-for-everyone',
                    }));
                    return;
                }
                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({
                    success: true,
                    revoked,
                    requested: targetCount,
                    partial: revoked < targetCount,
                }));
            } catch (err) {
                console.error('[WA] Revoke error:', safeErrorLabel(err));
                res.writeHead(err.statusCode || 500, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: err.message }));
            }
        return;
    }

    res.writeHead(404); res.end();
});

server.on('error', (err) => {
    if (err.code === 'EADDRINUSE') {
        console.error(`[WA] Port ${PORT} busy, retry in 3s...`);
        setTimeout(() => { server.close(); server.listen(PORT, '127.0.0.1'); }, 3000);
    } else { throw err; }
});

server.listen(PORT, '127.0.0.1', () => {
    console.log(`[WA] HTTP server ready → http://127.0.0.1:${PORT}`);
});
