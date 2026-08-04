<div align="center">
  <h1>Maya AI — Intelligent Desktop Agent</h1>
  <img src="assets/maya_ai_banner.png" alt="Maya AI Banner" width="800"/>
  
  **Voice-powered desktop automation with multilingual support**
  
  [![Windows](https://img.shields.io/badge/Windows-10%2F11-0078D6?logo=windows)]()
  [![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python)]()
  [![License](https://img.shields.io/badge/License-MIT-green)]()
  
  [Features](#features) • [Quick Start](#quick-start) • [Architecture](#architecture) • [Security](#security)
</div>

---

## Overview

Maya is a privacy-first desktop AI agent that understands natural language commands in **English, Bengali (Banglish), and Hindi (Hindilish)**. It runs entirely on your local machine, controlling desktop applications, managing communications, and automating workflows through voice or text input.

**Key Differentiator:** Native support for Indian English variations and romanized Indian languages, making it the first truly multilingual desktop agent optimized for South Asian users.

---

## Features

### Communication
- **WhatsApp Integration** — Send messages and files by contact name with intelligent fuzzy matching
- **Email Management** — Read, compose, send, and delete emails via Gmail
- **Telegram Bot** — Remote control your PC from your mobile device
- **Contact Resolution** — Automatically resolves partial names and handles disambiguation

### Desktop Control
- **Application Management** — Launch, focus, and terminate applications
- **System Controls** — Adjust volume, brightness, WiFi, Bluetooth settings
- **Power Management** — Lock, shutdown, restart, sleep, hibernate
- **Wallpaper Automation** — Automated wallpaper management with theme-based selection and user feedback learning

### Vision Capabilities
- **Outfit Analysis** — Real-time camera feedback for appearance and clothing coordination
- **Object Recognition** — Analyze and describe objects shown to camera
- **Screenshot Analysis** — Capture and process screen content on demand

### Media & Entertainment
- **YouTube Integration** — Play videos and music with voice commands
- **Background Audio** — Ad-free audio playback via VLC backend
- **Media Controls** — Play, pause, stop, volume control

### File Operations
- **Intelligent Search** — Cross-drive file search with smart filtering
- **File Management** — Create, read, delete, organize files and directories
- **Document Processing** — Read and extract content from PDFs and text files

### Web Automation
- **Browser Control** — Automated navigation and form filling via Playwright
- **Web Search** — Integrated web search with content extraction
- **Data Retrieval** — Fetch YouTube statistics, news, and structured web data

### Advanced Features
- **Multi-Intent Detection** — Execute multiple commands from a single utterance
- **Contextual Memory** — Remembers user preferences and conversation history
- **Language Auto-Detection** — Seamlessly switches between English, Banglish, and Hindilish
- **Voice I/O** — Full voice interaction with wake-word support

---

## Use Cases

### Professional Workflow
```
"Open Chrome in Nirupam profile"
"Check my emails"
"Set volume to 30"
"Search for Python async tutorial"
```

### Communication
```
"Send WhatsApp message to Mom: I'll be late for dinner"
"Read my latest emails"
"Send report.pdf to boss via email"
```

### Daily Tasks
```
"Open YouTube and play music"
"Set wallpaper to nature theme"
"Turn on WiFi"
"Take a screenshot"
```

### Personal Assistant
```
"How does my outfit look?" [activates camera]
"What's the weather today?"
"Search for nearby restaurants"
"Set volume to 50 and open Spotify"
```

---

## Quick Start

### Prerequisites
- **OS:** Windows 10 or Windows 11
- **Python:** 3.10 or higher
- **Node.js:** 18.x or higher
- **API Key:** Gemini API key ([obtain free key](https://aistudio.google.com/app/apikey))

### Installation

```bash
# Clone repository
git clone https://github.com/yourusername/maya-ai.git
cd maya-ai

# Install all dependencies
npm run install:all

# Configure API key
# Create .env file in project root:
echo "GEMINI_API_KEY=your_key_here" > .env

# Launch
npm start
```

Maya will be available at `http://localhost:8000`

---

## Architecture

### System Design

```
┌─────────────────────────────────────────────┐
│          User Input (Voice/Text)            │
└──────────────────┬──────────────────────────┘
                   │
       ┌───────────▼────────────┐
       │  Universal Intent AI   │  ← 30+ intent classification
       │  (Gemini-powered)      │     Multi-language support
       └───────────┬────────────┘
                   │
     ┌─────────────┼──────────────┐
     │             │              │
     ▼             ▼              ▼
┌─────────┐  ┌──────────┐  ┌──────────┐
│ Desktop │  │Messaging │  │   Web    │
│ Control │  │ Channels │  │Automation│
│         │  │          │  │          │
│ • Apps  │  │ • WhatsApp│ │ • Browser│
│ • System│  │ • Telegram│ │ • Search │
│ • Media │  │ • Email   │ │ • Extract│
└─────────┘  └──────────┘  └──────────┘
     │             │              │
     └─────────────┼──────────────┘
                   │
       ┌───────────▼────────────┐
       │   Execution Engine     │  ← <10ms for common ops
       │   + Safety Layer       │     Approval gates
       └────────────────────────┘
```

### Technology Stack

| Component | Technology |
|-----------|------------|
| **AI Engine** | Google Gemini 2.5/3.5 with multi-provider fallback |
| **Intent Classification** | LLM-based universal intent system (30+ intents) |
| **Voice Processing** | Gemini Audio, Whisper ASR, Edge TTS, Silero VAD |
| **Desktop Automation** | PyAutoGUI, PyGetWindow, mss, EasyOCR |
| **Browser Automation** | Playwright (async) |
| **Messaging** | whatsapp-web.js (Node.js), python-telegram-bot, SMTP |
| **Storage** | SQLite with AES-256 encryption |
| **Backend** | Python 3.10+ (FastAPI framework) |
| **Frontend** | React + Vite + Tauri |

### Multi-Agent Orchestration

Maya employs a specialized agent architecture:

- **Router Agent** — Intent classification and agent selection
- **OS Executor** — Desktop operations and system control
- **Coder Agent** — File operations and script execution
- **Researcher Agent** — Web search and information retrieval
- **Chat Agent** — Conversational responses

**Fast-Path Optimization:** Common commands (<50 characters) bypass LLM classification for sub-10ms latency.

---

## Security

### Privacy-First Design

| Aspect | Implementation |
|--------|---------------|
| **Data Location** | 100% local — no cloud storage |
| **Encryption** | Hardware-bound AES-256 for all sensitive data |
| **API Calls** | Only to configured LLM providers (user-controlled) |
| **Screen Capture** | Blocked when banking/password managers detected |
| **Audit Trail** | Comprehensive logging of all actions to `audit.jsonl` |

### Permission System

- **Granular Controls** — Enable/disable tool categories independently
- **Approval Gates** — Dangerous operations require explicit user confirmation
- **Emergency Stop** — Instant kill switch for all background processes
- **Session Isolation** — Per-session permission scopes

### Authentication & Encryption

- **Hardware Binding** — Encryption keys derived from CPU and motherboard serial numbers
- **App Passwords** — Gmail integration via dedicated app passwords (2FA required)
- **WhatsApp Security** — End-to-end encrypted via official WhatsApp Web protocol
- **Token Protection** — API keys encrypted at rest, never logged

---

## Performance

### Latency Benchmarks

| Operation Type | Latency | Method |
|---------------|---------|--------|
| Simple Commands | <1ms | Regex fast-path |
| App Control | <10ms | Pattern matching |
| Intent Classification (cached) | <5ms | Cache lookup |
| Intent Classification (uncached) | 50-200ms | LLM call |
| Camera Analysis | ~2-3s | Vision model |
| WhatsApp Send | ~500ms | Node.js service |

### Optimization Strategies

1. **Fast-Path Routing** — 80% of commands skip LLM entirely
2. **Aggressive Caching** — Intent classification results cached (90%+ hit rate expected)
3. **Async Execution** — Non-blocking I/O for all external calls
4. **Provider Fallback** — Multi-tier model cascade minimizes downtime

---

## Multilingual Support

### Supported Languages

| Language | Script | Auto-Detection | Example |
|----------|--------|----------------|---------|
| **English** | Latin | ✅ | "Open Chrome and set volume to 50" |
| **Banglish** | Latin | ✅ | "Chrome kholo and volume 50 koro" |
| **Hindilish** | Latin | ✅ | "Chrome kholo aur volume 50 karo" |

**Note:** Bengali and Hindi are supported in **romanized form only** (Latin script). Native Devanagari and Bengali scripts are automatically transliterated to Latin.

### Language Detection

- **Automatic:** Detects user's language from input patterns
- **Context-Aware:** Maintains language consistency across conversation
- **Mixed Input:** Handles code-switching naturally

---

## Comparison with Similar Systems

| Feature | Maya | OpenClaw | Hermes Agent |
|---------|------|----------|--------------|
| **Messaging Platforms** | Telegram, WhatsApp | WhatsApp, Slack, Signal, others | 20+ platforms |
| **Desktop Control** | ✅ Full (volume, WiFi, BT, power) | ❌ Limited | ❌ Basic |
| **Camera/Vision** | ✅ Outfit analysis, object recognition | ❌ | ❌ |
| **Wallpaper Management** | ✅ Theme-based with learning | ❌ | ❌ |
| **Indian Language Support** | ✅ Native Banglish/Hindilish | ❌ English only | ⚠️ Limited |
| **Multi-Intent Execution** | ✅ Advanced | ❌ Sequential only | ✅ |
| **Local Execution** | ✅ | ✅ | ✅ |
| **Voice I/O** | ✅ Multilingual | ❌ | ✅ English |
| **Self-Improvement** | Roadmap | ❌ | ✅ |
| **Calendar Integration** | Roadmap | ❌ | ✅ |
| **Cron Scheduler** | Roadmap | ❌ | ✅ |

**Maya's Competitive Edge:**
- Superior Windows desktop integration
- First-class Indian language support
- Advanced vision capabilities
- Granular system control

---

## Configuration

### Environment Variables

Required in `.env` file:

```env
# Required
GEMINI_API_KEY=your_gemini_api_key

# Optional
ELEVENLABS_API_KEY=your_elevenlabs_key  # Voice cloning
OPENAI_API_KEY=your_openai_key          # Fallback provider
```

### WhatsApp Setup

1. Initiate pairing: "Connect WhatsApp with my phone number"
2. Enter pairing code on mobile device under **Linked Devices**
3. Session persists across restarts (one-time setup)

### Email Configuration

1. Enable **2-Factor Authentication** on Google account
2. Generate **App Password** for Maya
3. Store credentials via conversational setup: "Save my email as user@gmail.com and password as APP_PASSWORD"
4. Credentials are encrypted with hardware-bound keys

### MCP Servers (Optional)

Edit `backend/config/mcp_servers.json` to add Model Context Protocol servers:

```json
{
  "mcpServers": {
    "memory": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-memory"]
    }
  }
}
```

---

## Extending Maya

### Custom Skills

Drop Markdown files in `backend/skills/` for hot-reloadable skills:

```markdown
# Weather Briefing Skill

When user says "morning briefing":
1. Fetch weather forecast
2. Read calendar for today
3. Check latest emails
4. Summarize news headlines
```

No restart required — skills are loaded on demand.

### Event Hooks

React to system events via Python scripts in `hooks/`:

```python
# hooks/on_sensitive_app_detected.py
def handle(event):
    if "banking" in event["window_title"].lower():
        disable_screen_capture()
        send_notification("Screen capture blocked for security")
```

Supported events: `on_session_start`, `on_command_approval_request`, `on_sensitive_app_detected`

---

## Troubleshooting

### Common Issues

**Symptom:** Slow initial responses (~200ms)
- **Cause:** Cold start LLM call
- **Solution:** Normal behavior; subsequent calls are cached (<5ms)

**Symptom:** WhatsApp "not connected" error immediately after startup
- **Cause:** Service initialization takes 30-60 seconds
- **Solution:** Wait for connection; Maya auto-retries for 90 seconds

**Symptom:** Camera preview fails with blank screen
- **Cause:** Camera permissions or in-use by another app
- **Solution:** Grant permissions in Windows Settings; close other camera apps

**Symptom:** Contact not found despite being in phone
- **Cause:** Name mismatch between Maya database and phone contacts
- **Solution:** Use exact name or phone number directly

**Symptom:** API quota exceeded errors
- **Cause:** Free-tier Gemini limits (e.g., 20 requests/day)
- **Solution:** Quotas reset daily; critical flows use regex fallback

---

## Roadmap

### Planned Features

**Q2 2026:**
- [ ] Persistent cross-session memory
- [ ] Google Calendar integration
- [ ] Slack/Discord messaging support

**Q3 2026:**
- [ ] Cron-based scheduled tasks
- [ ] GitHub/GitLab integration
- [ ] iOS/Android mobile app

**Q4 2026:**
- [ ] Self-improvement learning loop
- [ ] Subagent delegation for parallel tasks
- [ ] Docker/SSH backend support

---

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### How to Contribute

1. **Report Bugs** — Submit detailed issue reports
2. **Feature Requests** — Propose new capabilities with use cases
3. **Code Contributions** — Submit pull requests with tests
4. **Documentation** — Improve guides and examples

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Acknowledgments

Built with open-source tools:
- **AI:** Google Gemini API, OpenAI Whisper
- **Automation:** Playwright, PyAutoGUI
- **Messaging:** whatsapp-web.js, python-telegram-bot
- **Frontend:** React, Vite, Tauri

Special thanks to the open-source community.

---

<div align="center">
  
  **Developed in India 🇮🇳 for Global Users 🌍**
  
  [⭐ Star on GitHub](https://github.com/yourusername/maya-ai) • [📝 Report Issue](https://github.com/yourusername/maya-ai/issues) • [� Documentation](https://github.com/yourusername/maya-ai/wiki)
  
</div>
