/**
 * Maya AI — WhatsApp Service (whatsapp-web.js)
 * Features: text messaging, single/multiple file sending, delivery confirmation.
 */

const { Client, LocalAuth, MessageMedia } = require('whatsapp-web.js');
const fs   = require('fs');
const path = require('path');
const http = require('http');

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

    c.on('authenticated', () => {
        console.log('[WA] Authenticated!');
        connectionStatus = 'authenticated';
        pendingPhone = null;
    });

    c.on('auth_failure', (msg) => {
        console.error('[WA] Auth failure:', msg);
        connectionStatus = 'disconnected';
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
        // Only reconnect if this wasn't triggered by our own destroy() call
        if (!intentionalStop) {
            scheduleReconnect(5000);
        }
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
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
    if (req.method === 'OPTIONS') { res.writeHead(200); res.end(); return; }

    async function ensureConnected() {
        // Both 'connected' and 'authenticated' states can send messages in WhatsApp Web
        if (connectionStatus === 'connected' || connectionStatus === 'authenticated') return true;
        // If still initializing, wait briefly
        for (let i = 0; i < 10; i++) {
            await new Promise(r => setTimeout(r, 1000));
            if (connectionStatus === 'connected' || connectionStatus === 'authenticated') return true;
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
