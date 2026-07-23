<div align="center">
  <h1>Maya AI — Desktop Copilot</h1>
  <img src="assets/maya_ai_banner.png" alt="Maya AI Banner" width="800"/>
  <p><i>A privacy-first, voice-enabled AI assistant that runs locally on Windows.</i></p>
</div>

---

Maya is a context-aware desktop agent, not just a chatbot. She runs entirely on your PC, speaks and listens in Bengali, Hindi, and English, controls your desktop and browser, sends WhatsApp messages and emails on your behalf, and remembers you across sessions — all behind hardware-bound encryption and explicit permission gates.

## Table of Contents

- [Highlights](#highlights)
- [Feature Overview](#feature-overview)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running](#running)
- [Extending Maya](#extending-maya)
- [Security Model](#security-model)
- [Troubleshooting](#troubleshooting)

## Highlights

- **Multilingual by design** — replies in the language you speak (Bengali, Banglish, Hindi, English), in voice and text.
- **Local-first** — the backend, memory database, and automation stack run on your machine. Cloud calls are limited to the LLM/TTS providers you configure.
- **Remote control** — drive your PC from your phone through Telegram, with interactive approval buttons and an emergency stop.
- **WhatsApp automation** — send messages and files by contact name, with fuzzy name resolution and honest disambiguation when multiple contacts match.
- **Resilient** — multi-provider model fallback with active recovery probing, so a rate limit never takes Maya fully offline.

## Feature Overview

### Voice Engine

- **Input:** Silero VAD + faster-whisper transcription, with wake-word support (`openwakeword`).
- **Output:** Gemini native audio TTS by default, with automatic fallback to Microsoft Edge Neural TTS on network lag or rate limits.
- **Voice cloning:** optional adapters for local GPT-SoVITS (offline, port 9880) and ElevenLabs.
- **Bengali phonetics:** dedicated pronunciation rules for natural Bengali speech.

### WhatsApp Integration

Runs as a background Node.js service (`whatsapp-web.js`, port 9001) paired to your phone via a one-time pairing code — no QR scan needed.

- **Send messages and files by name.** Contact resolution order:
  1. Maya's own contact database,
  2. your phone's synced WhatsApp contacts, searched with fuzzy matching (partial names and small typos still match).
- **Ghost-contact filtering:** WhatsApp's internal LID migration creates duplicate contact entries with non-dialable IDs; these are detected and filtered out automatically.
- **Honest disambiguation:** if several contacts match, Maya shows you the exact numbered list — rendered deterministically in your language, never paraphrased by the LLM — and waits for your pick.
- **Incoming messages:** reads and summarizes recent chats, and can notify you (with context) when someone messages you or mentions Maya in a group.
- **Delivery tracking, revoke ("delete for everyone"), and per-sender block/allow lists.**
- **Security:** the service is protected by a per-boot 64-character API key generated in memory, shared via an ACL-restricted temp file, and injected into the Node subprocess — no manual key setup.

### Telegram Remote Control

- Command your PC from anywhere via a private Telegram bot.
- **Approval guard:** risky operations (shutdown, deletions, exec) require an explicit Approve/Deny tap before running.
- **Emergency stop:** a pinned red button (or sending `STOP` / `HALT` / `PANIC`) interrupts the orchestrator and force-kills every child process spawned by the agent (`taskkill /F /T`).

### Desktop & Web Automation

- **Three-tier automation strategy:** pre-mapped hotkeys for 60+ Windows actions → local OCR-assisted clicking (EasyOCR) with hover confirmation → Gemini Vision as the final fallback.
- **Browser automation:** async Playwright for navigation, form filling, and structured extraction; Google Meet auto-join and Google Classroom assignment submission.
- **Ad-free background music:** YouTube audio via VLC + yt-dlp, no browser window.
- **File search:** recursive drive search that skips heavy system folders (`AppData`, `node_modules`, `.git`) for fast results.
- **Background email:** SMTP (Gmail app password) with AES-encrypted credentials and file attachments.

### Multi-Agent Orchestration

- **Tiered routing:** simple chat bypasses the agent stack entirely; complex tasks route to specialized agents (Coder, OS Executor, Researcher).
- **Deterministic fast paths:** common OS controls (volume, brightness, app open/close) and clarification replies skip the LLM completely — instant and immune to model quality dips.
- **Cost-aware model tiering:** each message is scored for complexity and served by the matching Gemini tier, with automatic per-session downgrades on budget overrun.
- **Provider fallback chain:** Gemini → OpenRouter → NVIDIA NIM → OpenAI, with active recovery probing (exponential backoff: 30s → 60s → 120s → 300s) to restore the primary as soon as it recovers.

### Memory

- **Two-tier storage:** a sliding short-term conversation window feeds a nightly **Dreaming Mode** pass that distills durable facts, preferences, and contacts into encrypted long-term memory.
- **Semantic vector search:** `gemini-embedding-2` (3072-dim) vectors with local numpy similarity search over an encrypted SQLite store; weighted scoring combines similarity and importance, with gated retrieval to keep context compact.
- **Importance-based expiry:** trivia fades, critical facts persist; retrieval stats (`retrieval_count`, `last_accessed`) inform ranking.

### Live Canvas

- Generates interactive HTML widgets (dashboards, trackers) in a split-screen panel, synced in real time across voice, chat, and Telegram via WebSockets.

### Personality

- Four switchable modes — Companion, Coding, Professional, Friendly — with dynamic prompt assembly based on OS context and memory, and enforced religion-neutral language.

## Architecture

```
frontend/   React + Vite + Tauri desktop shell
            Zustand state, WebAudio gapless playback, voice orb UI
backend/    Python + FastAPI (localhost:8000)
  api/          REST + WebSocket handlers, Telegram bot
  brain/        orchestrator, multi-agent team, providers, memory, personality
  voice/        VAD, transcription, TTS routing, voice state machine
  tools/        desktop automation, browser, WhatsApp service (Node, port 9001)
  skills/       hot-reloadable SKILL.md skills + AST-sandboxed plugins
  system/       scheduler, state manager, hooks, observability
  config/       mcp_servers.json and platform config
```

| Layer | Stack |
|---|---|
| LLM | Gemini 2.5 / 3.x via `google-genai`, multi-provider fallback |
| Voice | Gemini native audio, Edge-TTS, faster-whisper, Silero VAD, GPT-SoVITS, ElevenLabs |
| Vision/Automation | PyAutoGUI, mss, PyGetWindow, EasyOCR, RapidFuzz, Playwright |
| Messaging | whatsapp-web.js (Node), python-telegram-bot, SMTP |
| Storage | SQLite with hardware-bound AES encryption |

## Requirements

- Windows 10/11
- Python 3.10+
- Node.js 18+ (for the frontend and the WhatsApp service)
- A Gemini API key ([free from Google AI Studio](https://aistudio.google.com/app/apikey))

## Installation

```bash
git clone https://github.com/palnirupam/maya-ai.git
cd maya-ai
npm run install:all
```

`install:all` creates the Python virtual environment and installs all Python and Node dependencies.

## Configuration

### 1. API keys

Create a `.env` file in the **project root**:

```env
GEMINI_API_KEY=your_gemini_api_key_here
ELEVENLABS_API_KEY=your_elevenlabs_key_here   # optional
```

### 2. Email (conversational — no files to edit)

1. Enable **2-Step Verification** on your Google account and generate an **App Password** named "Maya AI".
2. Tell Maya (Telegram or desktop chat): *"Save my email as you@gmail.com and password as abcdabcdabcdabcd"*.
3. Maya encrypts and stores the credentials locally. Background email is ready.

### 3. WhatsApp pairing

Ask Maya to connect WhatsApp with your phone number. She requests a pairing code from the background service; enter it on your phone under **Linked Devices**. The session persists across restarts — pairing is one-time.

### 4. MCP servers (optional)

Maya ships pre-configured with the Knowledge Graph memory server (`@modelcontextprotocol/server-memory`). Add any other MCP server (GitHub, PostgreSQL, Slack, …) in `backend/config/mcp_servers.json`, or simply tell Maya on Telegram to add one — she validates the package name and writes the config atomically.

## Running

```bash
npm start
```

This launches the FastAPI backend (`localhost:8000`) and the Vite frontend (`localhost:1420`) concurrently. The WhatsApp service and Telegram bot start automatically with the backend.

> **Note:** after a fresh start, the WhatsApp service takes ~30–60 seconds to reconnect. Maya waits for it automatically (up to 90 s) before sending, so messages issued during startup are delayed, not dropped.

## Extending Maya

- **Markdown skills:** drop a `SKILL.md` file into `backend/skills/` and Maya learns it instantly — hot-reloaded, no restart, no Python boilerplate.
- **Python plugins:** analyzed at the AST level before loading; dangerous imports (`os`, `eval`, `exec`) are rejected, and SHA-256 integrity checks detect tampering.
- **Event hooks:** run local scripts on events such as `on_session_start`, `on_sensitive_app_detected`, or `on_command_approval_request` — path-restricted to `hooks/`, with execution timeouts and a concurrency cap.

## Security Model

- **Hardware-bound encryption:** keys and credentials are AES-encrypted with a key derived from your motherboard and CPU serials — the database is useless if copied to another machine.
- **Permission gating:** tool categories (system control, screen capture, messaging) can be individually disabled; disabled tools are removed from the model's view entirely.
- **Exec approval and audit:** dangerous OS commands are queued for human approval, and every tool action is logged to `audit.jsonl`.
- **Screenshot protection:** if a password manager or banking tab is visible, screen capture is blocked; every screen inspection raises a visible Windows toast notification.
- **Deterministic user-facing errors:** clarification prompts and failure messages are template-rendered in your language rather than generated, so degraded model output can never leak internal instructions.

## Troubleshooting

| Symptom | Cause & fix |
|---|---|
| "WhatsApp is not connected" right after startup | The service needs ~30–60 s to reconnect. Maya retries for up to 90 s; just wait a moment. |
| Contact found on your phone but not by Maya | Check the saved spelling — fuzzy matching tolerates small typos but not entirely different names. You can always send by number directly. |
| Degraded or odd replies late in the day | Free-tier Gemini quotas (e.g. 20 requests/day per model) push Maya onto fallback models. Quotas reset daily; critical flows (contact lists, errors) are deterministic and unaffected. |
| MCP server fails to start with npm 404 | The package name in `backend/config/mcp_servers.json` doesn't exist on npm. Remove or correct the entry. |

<br>
<div align="center">
  <i>Built with care for a better AI desktop experience.</i>
</div>
