/**
 * Maya AI — WhatsApp Service (whatsapp-web.js)
 * Features: text messaging, single/multiple file sending, delivery confirmation.
 */

const { Client, LocalAuth, MessageMedia } = require('whatsapp-web.js');
const fs   = require('fs');
const path = require('path');
const http = require('http');
const crypto = require('crypto');

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

const PORT     = 9001;
const DATA_DIR = path.resolve(__dirname, '../../../../../data');
const AUTH_DIR = path.join(DATA_DIR, 'whatsapp_auth');

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
            console.log(`[WA] Loading ${percent}% — ${msg}`);
        }
    });

    // When QR fires, request pairing code if phone is pending
    c.on('qr', async (_qr) => {
        if (pendingPhone) {
            const phone = pendingPhone;
            try {
                console.log(`[WA] Requesting pairing code for ${phone}...`);
                const code = await c.requestPairingCode(phone);
                console.log(`[WA] Pairing code: ${code}`);
                pairingResult = { code, error: null };
            } catch (err) {
                console.error('[WA] requestPairingCode failed:', err.message);
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
        console.error('[WA] Auth failure:', msg);
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
            console.log(`[WA] Delivery update for ${msg.id._serialized}: ${sentMessageLog[msg.id._serialized]}`);
        }
    });

    c.on('disconnected', (reason) => {
        console.log(`[WA] Disconnected: ${reason} | intentional=${intentionalStop}`);
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
            console.log(`[WA-INCOMING] Queued: id=${uid} isGroup=${capturedIsGrp} from=${capturedNum}`);
        }, DEBOUNCE_MS);
    });

    console.log('[WA] Initializing Chrome + WhatsApp Web...');
    try {
        await c.initialize();
    } catch (err) {
        console.error('[WA] initialize() error:', err.message);
        if (!intentionalStop) scheduleReconnect(8000);
    }
}

// Start on boot
startClient(null);

// ── HTTP Server ───────────────────────────────────────────────────────────────
const server = http.createServer(async (req, res) => {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, x-api-key');
    if (req.method === 'OPTIONS') { res.writeHead(200); res.end(); return; }

    // API Key Validation
    const clientIp = req.socket.remoteAddress || 'unknown';
    const providedKey = req.headers['x-api-key'] || '';
    const expectedKey = process.env.WA_API_KEY || 'default_maya_key_change_me';
    
    if (!safeCompare(providedKey, expectedKey)) {
        if (!checkAuthRateLimit(clientIp)) {
            res.writeHead(429, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: "Too many authentication failures" }));
            return;
        }
        res.writeHead(401, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: "Unauthorized" }));
        return;
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

            console.log(`\n[WA] === PAIRING REQUEST for +${phone} ===`);

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
        let body = '';
        req.on('data', c => { body += c; });
        req.on('end', async () => {
            try {
                const { to, message } = JSON.parse(body);
                if (!to || !message) {
                    res.writeHead(400);
                    res.end(JSON.stringify({ error: 'Missing to or message' }));
                    return;
                }
                if (!(await ensureConnected())) {
                    res.writeHead(400, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ error: `Not connected (status: ${connectionStatus})` }));
                    return;
                }
                let num = to.replace(/\D/g, '');
                if (num.startsWith('00')) num = num.slice(2);
                else if (num.startsWith('0')) num = num.slice(1);
                if (num.length === 10) num = '91' + num;

                const chatId = `${num}@c.us`;
                console.log(`[WA] Checking if ${chatId} is registered...`);
                const isRegistered = await client.isRegisteredUser(chatId);
                if (!isRegistered) {
                    console.log(`[WA] Error: ${chatId} is not a registered WhatsApp user.`);
                    res.writeHead(400, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ error: `The number ${num} is not registered on WhatsApp.` }));
                    return;
                }

                console.log(`[WA] Sending to ${chatId}`);
                await client.sendMessage(chatId, message);
                console.log(`[WA] Sent OK to ${chatId}`);

                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ success: true }));
            } catch (err) {
                console.error('[WA] Send error:', err.message);
                res.writeHead(500, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: err.message }));
            }
        });
        return;
    }


    // ── Helper: normalize phone number ────────────────────────────────────────
    function normalizePhone(raw) {
        let num = raw.replace(/\D/g, '');
        if (num.startsWith('00')) num = num.slice(2);
        else if (num.startsWith('0')) num = num.slice(1);
        if (num.length === 10) num = '91' + num;
        return num;
    }

    // POST /send-file  { to, filePath, caption? }
    if (req.url === '/send-file' && req.method === 'POST') {
        let body = '';
        req.on('data', c => { body += c; });
        req.on('end', async () => {
            try {
                const { to, filePath, caption = '' } = JSON.parse(body);
                if (!to || !filePath) {
                    res.writeHead(400, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ error: 'Missing to or filePath' }));
                    return;
                }
                if (!(await ensureConnected())) {
                    res.writeHead(400, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ error: `Not connected (status: ${connectionStatus})` }));
                    return;
                }
                const absPath = path.resolve(filePath);
                if (!fs.existsSync(absPath)) {
                    res.writeHead(400, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ error: `File not found: ${absPath}` }));
                    return;
                }
                const num    = normalizePhone(to);
                const chatId = `${num}@c.us`;
                const isRegistered = await client.isRegisteredUser(chatId);
                if (!isRegistered) {
                    res.writeHead(400, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ error: `Number ${num} is not registered on WhatsApp.` }));
                    return;
                }
                console.log(`[WA] Sending file "${absPath}" → ${chatId}`);
                const media = MessageMedia.fromFilePath(absPath);
                const msg   = await client.sendMessage(chatId, media, { caption });
                const msgId = msg.id._serialized;
                sentMessageLog[msgId] = 'sent';
                console.log(`[WA] File sent OK. msgId=${msgId}`);
                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ success: true, messageId: msgId }));
            } catch (err) {
                console.error('[WA] send-file error:', err.message);
                res.writeHead(500, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: err.message }));
            }
        });
        return;
    }

    // POST /send-files  { to, files: [{ filePath, caption? }] }
    if (req.url === '/send-files' && req.method === 'POST') {
        let body = '';
        req.on('data', c => { body += c; });
        req.on('end', async () => {
            try {
                const { to, files } = JSON.parse(body);
                if (!to || !files || !Array.isArray(files)) {
                    res.writeHead(400, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ error: 'Missing to or files array' }));
                    return;
                }
                if (!(await ensureConnected())) {
                    res.writeHead(400, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ error: `Not connected (status: ${connectionStatus})` }));
                    return;
                }
                const num    = normalizePhone(to);
                const chatId = `${num}@c.us`;
                const isRegistered = await client.isRegisteredUser(chatId);
                if (!isRegistered) {
                    res.writeHead(400, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ error: `Number ${num} is not registered on WhatsApp.` }));
                    return;
                }
                const results = [];
                for (const item of files) {
                    const absPath = path.resolve(item.filePath);
                    const caption = item.caption || '';
                    if (!fs.existsSync(absPath)) {
                        results.push({ file: item.filePath, success: false, error: 'File not found' });
                        continue;
                    }
                    try {
                        console.log(`[WA] Sending file "${absPath}" → ${chatId}`);
                        const media = MessageMedia.fromFilePath(absPath);
                        const msg   = await client.sendMessage(chatId, media, { caption });
                        const msgId = msg.id._serialized;
                        sentMessageLog[msgId] = 'sent';
                        results.push({ file: item.filePath, success: true, messageId: msgId });
                        console.log(`[WA] File sent OK. msgId=${msgId}`);
                    } catch (fileErr) {
                        results.push({ file: item.filePath, success: false, error: fileErr.message });
                    }
                    // 600ms delay between files to avoid WhatsApp rate-limiting
                    await new Promise(r => setTimeout(r, 600));
                }
                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ success: true, results }));
            } catch (err) {
                console.error('[WA] send-files error:', err.message);
                res.writeHead(500, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: err.message }));
            }
        });
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
            console.log(`[WA] Status check for ${messageId}: ${status}`);
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ messageId, status }));
        } catch (err) {
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
            console.error('[WA fetch-messages] Internal error:', err);
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
        let body = '';
        req.on('data', c => { body += c; });
        req.on('end', async () => {
            try {
                const { chatId: toChatId, message } = JSON.parse(body);
                if (!toChatId || !message) {
                    res.writeHead(400, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ error: 'Missing chatId or message' }));
                    return;
                }
                if (!(await ensureConnected())) {
                    res.writeHead(400, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ error: `Not connected (status: ${connectionStatus})` }));
                    return;
                }
                console.log(`[WA-INCOMING] Sending reply to chatId=${toChatId}`);
                await client.sendMessage(toChatId, message);
                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ success: true }));
            } catch (err) {
                console.error('[WA-INCOMING] Reply error:', err.message);
                res.writeHead(500, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: err.message }));
            }
        });
        return;
    }

    // ── POST /register-known  { number } ─────────────────────────────────────
    if (req.url === '/register-known' && req.method === 'POST') {
        let body = '';
        req.on('data', c => { body += c; });
        req.on('end', () => {
            try {
                const { number } = JSON.parse(body);
                if (number) {
                    knownSenders.add(String(number));
                    console.log(`[WA-INCOMING] Registered known sender: ${number}`);
                    res.writeHead(200, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ success: true }));
                } else {
                    res.writeHead(400); res.end(JSON.stringify({ error: 'Missing number' }));
                }
            } catch (e) { res.writeHead(400); res.end(JSON.stringify({ error: e.message })); }
        });
        return;
    }

    // ── POST /block-number  { number } ───────────────────────────────────────
    if (req.url === '/block-number' && req.method === 'POST') {
        let body = '';
        req.on('data', c => { body += c; });
        req.on('end', () => {
            try {
                const { number } = JSON.parse(body);
                if (number) {
                    blockedSenders.add(String(number));
                    knownSenders.delete(String(number));
                    console.log(`[WA-INCOMING] Blocked sender: ${number}`);
                    res.writeHead(200, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ success: true }));
                } else {
                    res.writeHead(400); res.end(JSON.stringify({ error: 'Missing number' }));
                }
            } catch (e) { res.writeHead(400); res.end(JSON.stringify({ error: e.message })); }
        });
        return;
    }

    // ── POST /revoke  { toChatId, count } ─────────────────────────────────────
    if (req.url === '/revoke' && req.method === 'POST') {
        let body = '';
        req.on('data', c => { body += c; });
        req.on('end', async () => {
            try {
                const { toChatId, count } = JSON.parse(body);
                if (!toChatId) {
                    res.writeHead(400, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ error: 'Missing toChatId' }));
                    return;
                }
                if (!(await ensureConnected())) {
                    res.writeHead(400, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ error: `Not connected` }));
                    return;
                }
                console.log(`[WA] Fetching messages for ${toChatId} to revoke...`);
                const chat = await client.getChatById(toChatId);
                const messages = await chat.fetchMessages({ limit: 50 });
                let revoked = 0;
                const targetCount = count || 1;
                for (let i = messages.length - 1; i >= 0; i--) {
                    if (messages[i].fromMe) {
                        await messages[i].delete(true); // true = delete for everyone
                        revoked++;
                        if (revoked >= targetCount) break;
                        await new Promise(r => setTimeout(r, 800));
                    }
                }
                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ success: true, revoked }));
            } catch (err) {
                console.error('[WA] Revoke error:', err.message);
                res.writeHead(500, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: err.message }));
            }
        });
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
