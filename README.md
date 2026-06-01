<div align="center">
  <h1>✨ Maya AI - The Next Gen Desktop Copilot</h1>
  <br/>
  <img src="assets/maya_ai_banner.png" alt="Maya AI Banner" width="800"/>
  <br/>
  <p><i>A privacy-first, fully autonomous, and highly emotional AI companion for Windows.</i></p>
</div>

---

Maya is not just a chatbot—she is a **Context-Aware Desktop Agent** designed to run locally on your PC. Equipped with powerful voice cloning, hybrid vision automation, and enterprise-grade privacy controls, Maya acts as your pair programmer, assistant, and companion.

## 🌟 Key Features

### 🗣️ Immersive Voice Engine (GPT-SoVITS)
Maya doesn't sound like a robot. She is powered by a localized **GPT-SoVITS Engine**, allowing for ultra-realistic voice cloning with dynamic emotion control.
* 🎙️ **VAD Pipeline:** Uses Silero VAD + Faster Whisper to transcribe your voice perfectly.
* 🎭 **Emotion Control:** She dynamically changes her voice tone (Happy, Sad, Angry, Cute, Romantic) based on context.
* 🔄 **Smart Fallback:** If local TTS is busy, she seamlessly falls back to Microsoft Edge Neural TTS.

### 📱 Remote Mobile Control (Telegram & WhatsApp)
Maya bridges the gap between your desktop and mobile phone with native integrations.
* 🤖 **Telegram Remote Control:** Command your laptop from anywhere via a secure Telegram Bot.
  * ⚠️ **Dangerous Command Guard:** Prompts with interactive Yes/No buttons before executing risky operations like shutting down the PC.
  * 🚨 **🛑 Emergency Kill Switch:** Features a prominent, red **Emergency Stop** button at the very top of the Telegram bot keyboard! Tapping the button or sending `STOP`, `HALT`, `PANIC` instantly interrupts and kills any running orchestrator task or runaway automation in the backend, ensuring 100% host safety.
* 💬 **WhatsApp Integration:** 
  * 📨 **Background Message Reading & Sending:** Maya natively reads recent WhatsApp chats and summarizes them via the background service. You can ask *"Did Pintu send any new messages?"* straight from Telegram without opening your PC.
  * 🔒 **Zero-Config Auto-Auth Security:** Features an enterprise-grade dynamic token injection. A cryptographically secure 64-character key (`secrets.token_hex`) is generated in memory, securely shared via atomic Temp files (`icacls` restricted), and injected directly into the Node.js subprocess. No `.env` manual setups required—100% robust and hack-proof out of the box!
* 📬 **Headless Background Emailer:** Send secure emails completely in the background via SMTP (Gmail) using AES-GCM encrypted credentials. Fully supports **file attachments** (send any PDF, image, or document from your PC remotely).
* 🔍 **Recursive PC File Search:** Locates any file on your hard drives in seconds. Highly optimized to skip heavy system/dependency folders (like `AppData`, `node_modules`, `.git`) for fast, crash-free indexing.
* ⚡ **Lightning Fast Routing:** Optimized Gemini API adapters auto-route between `gemini-3.5-flash` and `gemini-2.5-flash` for sub-3-second mobile replies.

### 👁️ Context-Aware Vision Architecture
Maya can see your screen, but **only when you ask her to**. 
* **Hybrid Automation (3-Tier Strategy):**
  1. ⚡ **Blind Macros & Shortcuts:** Lightning-fast pre-mapped hotkeys for over 60+ Windows actions (Virtual Desktops, Window Snapping, Brightness Control, Media).
  2. 🔍 **OCR-Assisted Clicking:** Maya scans the screen locally (using `EasyOCR` + `Pillow`) to find exact words and buttons. She hovers for visual confirmation before clicking!
  3. 🧠 **Gemini Vision Fallback:** Uses Gemini 1.5 Flash for deep visual reasoning.
* **App Context System:** Before working in a new app, Maya automatically reads a dedicated JSON knowledge base (`app_contexts/`) to learn the app's specific shortcuts and workflows.

### 🌐 Advanced Browser & Web Automation
Maya can natively interact with the web without manual mouse clicking.
* 🎭 **Playwright Integration:** Native `async` Playwright engine allows Maya to navigate, click, type, and extract structured data from any website programmatically.
* 🎥 **Google Meet Automation:** Automatically joins Meet calls, manages mic/camera state, and handles attendance.
* 📚 **Google Classroom Automation:** Fetches pending assignments and programmatically uploads & submits files to Classroom.
* 🎵 **Headless Ad-Free YouTube:** Play background music directly via VLC + yt-dlp without opening a browser or playing a single ad!

### 🧠 Intelligent Multi-Agent System
Maya operates on a sophisticated **4-Tier Routing Architecture**, ensuring maximum efficiency:
* **Smart Routing:** Simple chats bypass agents for instant replies, while complex tasks are delegated to specialized agents (Coder, OS Executor, Researcher).
* **Multi-Provider Fallback Chain:** Never goes offline! Automatically routes requests: `Gemini → OpenRouter → NVIDIA NIM → OpenAI`. If one rate-limits, the next one instantly takes over.
* **Safety First:** Built-in capability gating (tools are disabled if not explicitly permitted), safety timeouts, and infinite-loop constraints.

### 🛡️ Enterprise-Grade Security & Sandboxing
Spyware is creepy. Maya is transparent and mathematically secure.
* **Hardware-Bound AES-256 Encryption:** Your keys and passwords are encrypted using a cryptographic key derived natively from your Motherboard + CPU serial. They cannot be stolen and decrypted on another PC.
* **AST-Based Skill Sandboxing:** Community plugins and skills are analyzed at the source level. Dangerous imports (`os`, `eval`, `exec`) are strictly blocked before execution.
* **Cryptographic Integrity:** SHA-256 hash verification ensures loaded plugins haven't been maliciously tampered with.
* **Sensitive App Auto-Blocker:** If you have Bitwarden, 1Password, or a Bank tab open, Maya physically **blocks the screenshot** to protect your passwords and OTPs.
* **Visual Overlay Feedback:** A Windows Toast Notification (`👁️ Maya is inspecting Chrome...`) pops up every single time she looks at your screen. You are always in control.

### 💾 3-Layer Encrypted Memory
Maya actually remembers you. 
* **Tri-Tier Storage:** Contextually divides memory into *Short-term Conversation*, *Emotional State*, and *Long-term Facts*.
* **Importance-Based Expiry:** Irrelevant details fade away over time, while critical facts are retained forever.
* **Secure Storage:** All memories are saved in a fully encrypted local SQLite database.

### 🎭 Dynamic Contextual Personality
Maya isn't just a bot, she has highly adaptable modes.
* **4 Personality Modes:** Seamlessly switch between *Companion*, *Coding*, *Professional*, and *Friendly*.
* **Religion-Neutral Enforcement:** Strictly enforces unbiased, respectful, and religion-neutral language in all interactions.
* **Bengali Phonetic TTS:** Specialized linguistic rules mapped for flawless Bengali pronunciation during Text-to-Speech.
* **Dynamic Prompt Assembly:** System prompts aren't static; they are built on-the-fly based on your current OS context and emotional memory.

### 🧩 Hot-Reloadable Plugin & Skill System
Maya grows with you.
* **Markdown-Based Skills:** Create custom skills instantly. Maya extends her own capabilities by reading `SKILL.md` files—no complex python boilerplate required!
* **Hot-Reloading:** Drop a new plugin or skill into the folder, and Maya learns it instantly without needing a server restart.

### 🔌 Universal MCP (Model Context Protocol) Support
Infinite capabilities without writing custom integrations.
* **Zero Custom Code:** Connect Maya to GitHub, SQLite, PostgreSQL, Slack, Google Drive, or Knowledge Graphs by simply adding a few lines to `mcp_servers.json`. No Python API integration needed!
* **Auto-Discovery:** Maya automatically connects to your defined MCP servers (via `stdio` or `sse`), discovers available tools dynamically, and sanitizes schemas to be fully compatible with Gemini.
* **Robust Concurrency:** Built with enterprise-grade asynchronous lifecycle management. Handles background task isolation, precise lock guards, and jittered exponential backoffs natively to prevent retry storms and deadlock scenarios.
* **Auto MCP Configurator via Telegram:** No need to edit JSON files manually! Just tell Maya on Telegram: *"Add the YouTube MCP server using @modelcontextprotocol/server-youtube and this API key."* Maya validates the package using strict regex, sanitizes environment variables to prevent RCE/Shell Injection, and safely updates `mcp_servers.json` using atomic file writes (`os.replace`). *(e.g. get your YouTube API v3 Key from the [Google Cloud Console](https://console.cloud.google.com/apis/library/youtube.googleapis.com)).*

---

## ⚙️ Initial Setup

1. **Clone the Repository**:
   First, clone the repository to your local machine:
   ```bash
   git clone https://github.com/palnirupam/maya-ai.git
   cd maya-ai
   ```

2. **API Keys Configuration**:
   Create a `.env` file in the `backend/` directory and add your keys. *(Get your Gemini API Key for free from [Google AI Studio](https://aistudio.google.com/app/apikey))*
   ```env
   GEMINI_API_KEY=your_gemini_api_key_here
   ELEVENLABS_API_KEY=your_elevenlabs_key_here # Optional
   ```

3. **📬 Headless Gmail Setup (No Files to Edit!)**:
   You do **not** need to open any code files or edit `.env` to set up your email! Maya is fully conversational.
   * **Step 1:** Turn on **2-Step Verification** on your Google Account, search for **App Passwords**, name it "Maya AI", and copy the generated 16-letter code.
   * **Step 2:** Simply open the **Telegram Bot on your mobile phone** (or the desktop chat interface) and tell Maya: 
     > *"Save my email as devnilasarker@gmail.com and password as ssfszsctppzaotlx"*
   * **Step 3:** Maya will automatically clean the password, encrypt the credentials securely, and save them in her local SQLite database. You're ready to send background emails! 🚀

4. **Install All Dependencies**:
   Open a terminal in the root `maya-ai` directory and run:
   ```bash
   npm run install:all
   ```
   *(This automatically creates the Python virtual environment and installs Node modules).*

## 🚀 Running the Application

Maya AI is configured to run both the frontend and backend concurrently in a single terminal.

```bash
npm start
```
*The backend will launch on `localhost:8000` and the frontend Vite dev server will open automatically.*

---

## 🛠️ Architecture Stack

### Backend (Python + FastAPI)
* **LLM Engine:** Gemini 2.5/3.5 Flash via `google-genai`
* **Multi-Agent Orchestrator:** Stateful task delegation across specialized sub-agents (Researcher, Coder, OS Executor) with safety timeouts and loop constraints
* **Voice:** Faster-Whisper, Silero VAD, GPT-SoVITS, Edge-TTS
* **Vision & Automation:** PyAutoGUI, mss, PyGetWindow, EasyOCR, RapidFuzz
* **Security:** AES-GCM Encrypted Settings, Sensitive App Keyword Blocking

### Frontend (React + Vite)
* **State Management:** Zustand
* **Audio:** WebAudio Context API (gapless queuing)
* **UI/UX:** Animated Voice Orb, Push-to-Talk, Markdown rendering

<br>
<div align="center">
  <i>Built with ❤️ for a better AI desktop experience.</i>
</div>
