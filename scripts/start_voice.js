const { spawn, execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const baseGptPath = path.join(__dirname, '..', 'GPT-SoVITS');
const logsDir = path.join(__dirname, '..', 'logs');
const logFile = path.join(logsDir, 'voice.log');

// Ensure logs directory exists
if (!fs.existsSync(logsDir)) {
  fs.mkdirSync(logsDir, { recursive: true });
}

// 1. Check if GPT-SoVITS folder exists
if (!fs.existsSync(baseGptPath)) {
  console.log('\x1b[33m[VOICE] GPT-SoVITS not installed in C:\\maya-ai\\GPT-SoVITS. Skipping advanced voice engine.\x1b[0m');
  process.exit(0);
}

// Check for nested extraction folder
let gptPath = baseGptPath;
if (fs.existsSync(path.join(baseGptPath, 'GPT-SoVITS-v4-20250529', 'api_v2.py'))) {
    gptPath = path.join(baseGptPath, 'GPT-SoVITS-v4-20250529');
}

// 2. Port Conflict Detection
try {
  // netstat returns 0 if it finds the port, 1 if it doesn't
  execSync('netstat -ano | findstr :9880 | findstr LISTENING', { stdio: 'ignore' });
  console.log('\x1b[33m[VOICE] Existing server detected on port 9880. Skipping startup.\x1b[0m');
  process.exit(0);
} catch (e) {
  // Port is free, proceed
}

console.log('\x1b[36m[VOICE] Starting GPT-SoVITS API Server on Port 9880...\x1b[0m');

// 3. Launch Process with redirection to log file
const outStream = fs.createWriteStream(logFile, { flags: 'a' });

const pythonExe = path.join(gptPath, 'runtime', 'python.exe');
let command = 'python';

// Use embedded python if it exists in the downloaded zip
if (fs.existsSync(pythonExe)) {
    command = pythonExe;
}

const voiceProcess = spawn(command, ['api_v2.py'], {
  cwd: gptPath,
  env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1', PYTHONUNBUFFERED: '1' },
  stdio: ['ignore', 'pipe', 'pipe'],
  windowsHide: true
});

voiceProcess.stdout.pipe(outStream);
voiceProcess.stderr.pipe(outStream);

console.log(`\x1b[36m[VOICE] Process spawned with PID: ${voiceProcess.pid}. Logs redirected to logs/voice.log\x1b[0m`);

// 4. Graceful Shutdown
const cleanup = () => {
  if (voiceProcess && !voiceProcess.killed) {
    console.log('\x1b[33m[VOICE] Shutting down Voice Engine...\x1b[0m');
    try {
        // Force kill the child process tree on Windows
        execSync(`taskkill /pid ${voiceProcess.pid} /T /F`, { stdio: 'ignore' });
    } catch(e) {}
  }
  process.exit();
};

process.on('SIGINT', cleanup);
process.on('SIGTERM', cleanup);
process.on('exit', cleanup);
