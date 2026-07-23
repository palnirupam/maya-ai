const path = require('path');
const fs = require('fs');

const MAX_BODY_BYTES = 256 * 1024;
const MAX_MESSAGE_LENGTH = 16 * 1024;
const MAX_CAPTION_LENGTH = 4096;
const MAX_BATCH_FILES = 10;
const DEFAULT_KEY = 'default_maya_key_change_me';

function validateApiKey(key) {
    if (typeof key !== 'string' || key.length < 32 || key === DEFAULT_KEY) {
        throw new Error('WA_API_KEY must be a strong random value of at least 32 characters');
    }
    return key;
}

function trustedOrigin(origin) {
    if (!origin) return null;
    try {
        const url = new URL(origin);
        if (!['http:', 'https:', 'tauri:'].includes(url.protocol)) return null;
        if (url.protocol === 'tauri:' || ['127.0.0.1', 'localhost', '::1'].includes(url.hostname)) {
            return origin;
        }
    } catch (_) {}
    return null;
}

function maskPhone(value) {
    const digits = String(value || '').replace(/\D/g, '');
    if (!digits) return '<unknown>';
    return digits.length <= 4 ? '****' : `...${digits.slice(-4)}`;
}

function safeAttachmentLabel(filePath) {
    const base = path.basename(String(filePath || ''));
    return base || '<unknown attachment>';
}

function safeErrorLabel(error) {
    const rawName = error && typeof error.name === 'string' ? error.name : '';
    const rawCode = error && typeof error.code === 'string' ? error.code : '';
    const name = /^(?:Error|[A-Za-z]{1,40}(?:Error|Exception))$/.test(rawName)
        ? rawName
        : 'Error';
    const code = /^[A-Z][A-Z0-9_.-]{0,31}$/.test(rawCode) && !/\d{5,}/.test(rawCode)
        ? rawCode
        : '';
    return code ? `${name} (${code})` : name;
}

function readJsonBody(req, maxBytes = MAX_BODY_BYTES) {
    return new Promise((resolve, reject) => {
        let size = 0;
        let settled = false;
        const chunks = [];
        req.on('data', chunk => {
            if (settled) return;
            const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
            size += buffer.length;
            if (size > maxBytes) {
                settled = true;
                const error = new Error('Request body too large');
                error.statusCode = 413;
                reject(error);
                return;
            }
            chunks.push(buffer);
        });
        req.on('end', () => {
            if (settled) return;
            try {
                settled = true;
                resolve(JSON.parse(Buffer.concat(chunks).toString('utf8')));
            } catch (_) {
                const error = new Error('Invalid JSON body');
                error.statusCode = 400;
                reject(error);
            }
        });
        req.on('error', error => {
            if (!settled) {
                settled = true;
                reject(error);
            }
        });
    });
}

function assertString(value, name, maxLength, { pattern, optional = false } = {}) {
    if (optional && (value === undefined || value === null || value === '')) return '';
    if (typeof value !== 'string' || value.length === 0 || value.length > maxLength) {
        const error = new Error(`${name} must be a non-empty string of at most ${maxLength} characters`);
        error.statusCode = 400;
        throw error;
    }
    if (pattern && !pattern.test(value)) {
        const error = new Error(`Invalid ${name}`);
        error.statusCode = 400;
        throw error;
    }
    return value;
}

function isPathInside(candidate, root) {
    const relative = path.relative(path.resolve(root), path.resolve(candidate));
    return relative === '' || (!relative.startsWith('..') && !path.isAbsolute(relative));
}

function assertSafeAttachment(filePath, options = {}) {
    const requested = path.resolve(assertString(filePath, 'filePath', 4096));
    const absolute = fs.existsSync(requested) ? fs.realpathSync(requested) : requested;
    const home = options.homeDir || process.env.USERPROFILE || process.env.HOME || '';
    const uploadRoot = options.uploadsDir || (options.dataDir && path.join(options.dataDir, 'uploads'));
    const roots = [
        options.projectRoot,
        options.dataDir,
        process.env.SystemRoot || 'C:\\Windows',
        process.env.ProgramFiles || 'C:\\Program Files',
        process.env['ProgramFiles(x86)'] || 'C:\\Program Files (x86)',
        home && path.join(home, 'AppData'),
        home && path.join(home, '.ssh'),
        home && path.join(home, '.aws'),
        home && path.join(home, '.azure'),
        home && path.join(home, '.config'),
    ].filter(Boolean);
    const base = path.basename(absolute).toLowerCase();
    const secretName = base === '.env' || base.startsWith('.env.') ||
        /^(credentials|secrets?|id_rsa|id_ed25519)(\.|$)/i.test(base) ||
        /\.(pem|key|p12|pfx)$/i.test(base);
    const allowedUpload = uploadRoot && isPathInside(absolute, uploadRoot);
    if (secretName || (!allowedUpload && roots.some(root => isPathInside(absolute, root)))) {
        const error = new Error('Attachment path is protected');
        error.code = 'PROTECTED_ATTACHMENT';
        error.statusCode = 403;
        throw error;
    }
    return absolute;
}

module.exports = {
    MAX_BODY_BYTES,
    MAX_MESSAGE_LENGTH,
    MAX_CAPTION_LENGTH,
    MAX_BATCH_FILES,
    validateApiKey,
    trustedOrigin,
    maskPhone,
    safeAttachmentLabel,
    safeErrorLabel,
    readJsonBody,
    assertString,
    assertSafeAttachment,
};
