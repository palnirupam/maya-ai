# Maya AI Desktop Product Delivery Roadmap

**Document type:** Remaining-work execution plan, architecture contract, release gates, and operations roadmap

**Target product:** Production-grade Maya AI desktop application

**Initial platform:** Windows 10 22H2 and Windows 11, x86-64

**Desktop host:** Tauri 2

**Application stack:** React/Vite, Rust/Tauri, packaged Python/FastAPI core, optional managed services

**Last revised:** 2026-07-22

**Current scope:** Desktop 1.0, signed updates, full capability qualification, and future subscription readiness

**Commercial scope:** Subscription implementation is deferred. Only the boundary required to add it safely later is included.

---

## 1. Purpose

This document contains only the remaining work required to turn the current Maya
repository into a normal, secure, installable, updateable Windows desktop
product.

Completed reliability work is not repeated as an open task. It appears only in
the verified foundation section so later phases know which behavior must be
preserved.

The plan defines:

- the product outcome;
- the target runtime architecture;
- the order of implementation;
- dependencies between work items;
- capability-by-capability qualification;
- voice and JARVIS-style realtime milestones;
- installer, signing, update, repair, and rollback behavior;
- the boundary for a future subscription system;
- evidence required before any item can be called complete.

In this roadmap, production-grade does not mean that software can never have a
future defect. It means every advertised behavior has an owner, a failure state,
an automated or approved live test, a recovery path, and release evidence.

---

## 2. Status and Evidence Rules

Every tracked item uses one of these states:

| Status | Meaning |
|---|---|
| NOT_STARTED | No qualifying implementation exists |
| IN_PROGRESS | Implementation exists but one or more required gates remain |
| BLOCKED | A named external decision, credential, certificate, environment, or dependency prevents progress |
| EXTERNAL | Deterministic work is complete, but an approved real service or device check remains |
| DONE | Implementation, tests, documentation, and required evidence all pass |

An item is not DONE because:

- source code exists;
- a developer-machine demo worked once;
- a fallback hid an error;
- the UI displayed a success message;
- a unit test covered only a helper;
- a dependency is listed but not packaged;
- a feature works only when Python, Node.js, npm, or Rust is installed globally.

Every DONE item must record:

- source commit;
- test command and result;
- artifact or runtime version;
- supported environment;
- known external dependency;
- migration or rollback consequence;
- security impact;
- user-visible failure behavior.

---

## 3. Verified Foundation - Preserve, Do Not Rebuild

The following foundation is already verified and is not active roadmap work:

- R09 final deterministic regression closure is complete.
- S01 cross-cutting security review is complete.
- The current deterministic backend suite and focused security suites pass.
- React/Vite, Tauri, FastAPI, SQLite, Telegram, WhatsApp integration, tools,
  permissions, approvals, verification, memory, Canvas, and voice foundations
  exist.
- Text, Telegram, WebSocket, and native voice reach the shared brain gateway and
  orchestrator.
- Core permission, protected-target, exact-argument approval, redaction,
  delivery-truth, and verifier behavior has regression coverage.
- Conversation rows and compacted archives use encrypted storage.
- Backend environment overrides for data, state, and selected log locations
  exist.
- Local-origin, loopback-host, WebSocket event-type, payload-size, and approval
  identifier validation exists.
- Gemini STT, Whisper fallback, sentence TTS providers, language-style handling,
  and frontend voice-session scaffolding exist.

These are regression invariants. Packaging, IPC, updater, or subscription work
must not weaken them.

Important boundary:

- Existing voice audit coverage proves shared command routing and selected
  safety behavior.
- It does not prove production microphone ownership, real playback completion,
  live barge-in, spoken approval, channel parity, or bidirectional realtime
  audio. Those remain explicit work below.

---

## 4. Desktop 1.0 Product Outcome

Desktop 1.0 is successful when a standard Windows user can:

1. Download one signed installer.
2. Install Maya per user without developer tools.
3. Launch Maya without a console window.
4. Complete resumable onboarding.
5. Configure an AI provider and optional communication services.
6. Use every installed and configured Maya capability through one coherent UI.
7. Talk to Maya naturally, interrupt it, approve or deny actions, and receive
   truthful progress and completion.
8. Close or quit Maya without leaving owned processes.
9. Restart after a backend or optional-service failure.
10. Update from the prior supported release without losing data or credentials.
11. Repair the application when files or optional components are damaged.
12. Uninstall while preserving user data unless removal is explicitly selected.
13. Export a redacted support bundle.
14. Continue receiving security updates without any account or subscription.

Desktop 1.0 must work without system installations of:

- Python;
- Node.js;
- npm;
- Rust;
- Cargo;
- a developer virtual environment;
- a repository checkout;
- a developer .env file.

---

## 5. Explicit Scope

### 5.1 Required for Desktop 1.0

- Windows x86-64 desktop packaging.
- Tauri-owned process lifecycle.
- Secure authenticated local IPC.
- Stable user data and secret storage.
- One microphone owner.
- Correct turn-based voice behavior.
- Gemini Live based realtime voice milestone.
- Complete tool and service readiness reporting.
- Optional component installation and isolation.
- Signed installer.
- Signed application updates.
- Database migration, backup, and recovery.
- Clean-machine qualification.
- Diagnostics and support bundle.
- Beta and stable release operations.

### 5.2 Deferred

- macOS and Linux distribution.
- Windows ARM64.
- Microsoft Store distribution.
- Enterprise MSI deployment.
- Multi-user Windows service installation.
- Mandatory Maya cloud account.
- Cloud synchronization of private memory.
- Billing, checkout, trials, license keys, feature paywalls, or subscriptions.
- Running the main AI process with administrator privileges.

---

## 6. Confirmed Architecture

These decisions remain the default unless an approved Architecture Decision
Record changes them with evidence.

| Area | Decision |
|---|---|
| Desktop framework | Tauri 2 |
| UI | React/Vite bundled inside Tauri |
| Core | Python/FastAPI packaged with PyInstaller onedir |
| Core ownership | Tauri launches and supervises the exact core process tree |
| IPC | Authenticated loopback HTTP/WebSocket on an OS-selected port |
| Runtime data | Windows per-user known folders, never the install directory |
| Secrets | Windows-protected secret store with verified legacy migration |
| Database | SQLite with exclusive migration lock, backup, integrity check, and schema version |
| Voice | One explicit microphone lease and one output session |
| Realtime voice | Provider-neutral interface, Gemini Live implementation first |
| Optional runtimes | Signed, versioned, independently repairable component packs |
| Installer | Per-user NSIS first |
| Updates | Tauri signed updater with internal, beta, and stable channels |
| Code signing | Authenticode for app, core, native binaries, and installer |
| Subscription | Provider-neutral access boundary now; no billing implementation |

### 6.1 Target Component Model

    Maya AI.exe - Tauri Host
      |
      +-- React UI
      |     +-- conversation and Canvas
      |     +-- voice session
      |     +-- approvals and task progress
      |     +-- settings and onboarding
      |     +-- components, diagnostics, updater, and recovery
      |
      +-- maya-core.exe - Packaged Python Sidecar
      |     +-- authenticated FastAPI and WebSocket
      |     +-- TurnCoordinator and channel adapters
      |     +-- orchestrator, tools, permissions, approvals, verifier
      |     +-- memory, scheduler, Canvas, audit, and diagnostics
      |     +-- voice provider and optional-service managers
      |
      +-- Optional Managed Components
            +-- WhatsApp Node and compatible browser runtime
            +-- Playwright browser
            +-- local STT models
            +-- local voice models
            +-- approved media binaries

### 6.2 Ownership Contract

The Tauri host owns:

- application single-instance enforcement;
- Windows runtime directory resolution;
- backend launch configuration;
- per-launch authentication token generation;
- READY protocol validation;
- exact process identity and Windows Job Object;
- bounded crash restart and safe mode;
- tray and window lifecycle;
- update download, verification, install, and recovery;
- application-level diagnostics.

The React UI owns:

- user interaction;
- foreground microphone capture;
- local audio scheduling and playback;
- approval and task-status presentation;
- onboarding;
- capability readiness and component management;
- update and recovery screens.

The Python core owns:

- AI orchestration;
- channel-neutral turn state;
- tools, permissions, approval binding, and verification;
- memory and database access;
- service readiness;
- realtime provider sessions;
- scheduler and automation;
- redacted audit evidence.

No layer may silently take ownership from another layer.

---

## 7. Non-Negotiable Product Invariants

### 7.1 Process and Runtime

- One app instance, one core owner, one database writer, and one microphone lease.
- The installation directory is read-only at runtime.
- The core binds only to 127.0.0.1 on port 0.
- Tauri tracks the exact core PID and owned descendants.
- User processes are never killed by image name or shared port.
- Parent loss causes bounded core self-termination.
- Optional-service failure does not crash core chat.

### 7.2 Security

- Every sensitive REST request requires the per-launch token.
- WebSocket authentication is the first frame and has a short timeout.
- The token is memory-only and never enters a URL, log, database, browser
  storage, crash report, or READY line.
- Strict origin, event allowlist, size, schema, and rate controls remain active.
- Dangerous actions require approval bound to session, tool, normalized
  arguments, and expiry.
- A future entitlement can never grant OS permission or bypass approval.
- All executable artifacts and update metadata are signed and verified.

### 7.3 Data and Privacy

- Database and mutable state live in per-user application directories.
- Every schema migration has a verified backup and integrity check.
- Legacy data is never deleted until the replacement passes a healthy launch.
- API keys, email credentials, Telegram tokens, WhatsApp secrets, and future
  refresh tokens use protected storage.
- Update-signing private keys never ship with or enter the desktop runtime.
- Logs never contain prompts, responses, message bodies, credentials, raw
  transcripts, full private paths, contacts, screenshots, or memory contents.
- Voice recording is ephemeral unless the user explicitly exports it.

### 7.4 Truthful Capability Behavior

Every feature reports one of:

- READY;
- NEEDS_SETUP;
- NEEDS_COMPONENT;
- BLOCKED_BY_PERMISSION;
- APPROVAL_REQUIRED;
- OFFLINE;
- DEGRADED;
- FAILED.

No missing dependency, provider fallback, rejected delivery, or unavailable
external service may be presented as success.

---

## 8. Capability Qualification Matrix

Desktop 1.0 cannot be called complete from chat-only testing. Each advertised
capability needs deterministic coverage, packaged-app coverage, and an approved
live check when the result depends on an external account or device.

| Capability | Desktop 1.0 qualification |
|---|---|
| AI providers | Configure, validate, switch, fail over truthfully, and redact keys |
| Conversation | Text and voice turns preserve session context and expose errors |
| Memory | Encrypted persistence, retrieval, compaction, migration, export, and corruption handling |
| Files and documents | Read, write, copy, move, rename, search, delete, organize, PDF/document handling, protected paths, and cross-drive behavior |
| Apps and windows | Open, focus, close, active-window actions, multi-window ambiguity, protected Maya processes, and truthful state |
| PC controls | Volume, brightness, lock, sleep, restart, shutdown, clipboard, process, battery, stats, Wi-Fi, and Bluetooth with correct approval |
| Browser and vision | Search, navigation, Playwright readiness, screen capture protection, OCR failure, and Canvas rendering |
| Email | Credential setup, search, read, send, attachment, destructive actions, idempotency, and approved live SMTP/IMAP evidence |
| WhatsApp | Pairing, allowlist, contact resolution, send, attachment, idempotency, reply workflow, optional runtime readiness, and approved live delivery |
| Telegram | Pairing, authorization, task progress, background completion, approval, cancellation, and voice-channel isolation |
| Voice | Mic ownership, VAD, STT, realtime input/output, spoken approval, progress, interruption, fallback, and privacy |
| Media | Play, pause, stop, volume, process ownership, missing runtime, and voice coexistence |
| Scheduler | Create, persist, run, cancel, recover, and avoid duplicate execution |
| Skills and MCP | Load, validate, isolate failure, enforce permission, and disable in safe mode |
| Settings | Persist truthfully, hot reload safely, and distinguish permission from readiness |
| Updates | Check, download, verify, defer safely, install, health-check, recover, and preserve data |

Release evidence must include a generated capability report showing:

- advertised features;
- implementation owner;
- permission state;
- runtime dependency;
- packaged test result;
- live external result or EXTERNAL reason;
- last verified version.

---

## 9. Execution Plan

The phases are dependency ordered. A later phase may prototype early, but it
cannot be declared DONE before its prerequisites.

### Phase 0 - Architecture Contract and Delivery Harness

**Estimate:** 3-5 engineering days

**Objective:** Freeze the product contracts that every later artifact uses.

**Deliverables:**

- ADR-001: Tauri host and process ownership.
- ADR-002: PyInstaller onedir sidecar.
- ADR-003: dynamic authenticated loopback IPC.
- ADR-004: Windows Job Object, restart, and safe-mode policy.
- ADR-005: runtime directory layout and data ownership.
- ADR-006: secret storage and legacy migration.
- ADR-007: foreground and background voice ownership.
- ADR-008: version and compatibility contract.
- One shared machine-readable release manifest containing:
  - app version;
  - core version;
  - API protocol;
  - database schema;
  - component-manifest version;
  - minimum supported prior release.
- A complete runtime and redistribution dependency inventory.
- A capability readiness schema.
- Initial Windows CI checks for Python, frontend, Node, Rust, secret scan, and
  dependency policy.

**Exit gates:**

- ADRs are reviewed.
- Host, UI, core, database, and component versions come from one release source.
- CI can fail a change before packaging begins.
- No unresolved architecture choice blocks Phases 1-3.

### Phase 1 - Runtime Data, Migration, and Protected Secrets

**Estimate:** 1-2 weeks

**Depends on:** Phase 0

**Objective:** Remove production dependence on the repository and make user data
survive installation and update.

**Deliverables:**

- Tauri resolves and creates:
  - data directory;
  - state directory;
  - cache directory;
  - logs directory;
  - backups directory;
  - temporary runtime directory.
- Tauri passes absolute paths to the core.
- Backend path configuration supports DATA, STATE, CACHE, LOG, BACKUP, and TEMP.
- Production mode rejects repository-relative mutable paths.
- Legacy-location migration provides:
  - explicit known-source detection;
  - preview;
  - exclusive lock;
  - destination collision policy;
  - copy and fsync;
  - database open and integrity validation;
  - encrypted-content validation;
  - rollback;
  - migration receipt;
  - source retention until a healthy launch.
- Numbered database schema migrations replace ad hoc startup alterations.
- A verified database backup is created before every schema migration.
- A database writer lock prevents simultaneous cores.
- Windows DPAPI or Credential Manager adapter is introduced.
- Existing encrypted credentials migrate only after write/read verification.
- Failed legacy decryption requests re-entry without leaking data.

**Required tests:**

- read-only installation directory;
- Unicode Windows user path;
- spaces and long paths;
- existing destination;
- interrupted migration;
- corrupt database;
- missing legacy key;
- second writer attempt;
- backup restore;
- upgrade fixture from every supported prior schema.

**Exit gates:**

- A production-mode core can run from a read-only application directory.
- Existing user data survives relocation.
- Failed migration leaves the original recoverable.
- No normal secret relies on a repository file.

### Phase 2 - Packaged Core and Authenticated IPC

**Estimate:** 2-3 weeks

**Depends on:** Phases 0-1

**Objective:** Produce a self-contained core and a versioned secure bootstrap.

**Deliverables:**

- packaging/pyinstaller/maya-core.spec.
- Explicit hooks for dynamic imports, ML/audio libraries, certificates, prompts,
  built-in skills, templates, and native binaries.
- Deterministic resource and exclusion manifests.
- Build and smoke-test scripts.
- PyInstaller onedir maya-core executable.
- Backend bind to 127.0.0.1 port 0.
- Per-launch 256-bit random token generated by Tauri.
- Environment-based parent PID, paths, release, protocol, and runtime mode.
- Machine-readable READY event containing non-secret port and version data.
- Minimal alive endpoint for the host.
- Authenticated detailed health endpoint.
- REST bearer or dedicated token header.
- WebSocket first-frame authentication with timeout and replay rejection.
- Runtime descriptor exposed to React through a narrow Tauri command.
- Frontend HTTP and WebSocket clients use the runtime descriptor.
- Dynamic-port-compatible CSP and origin configuration.
- UI refuses incompatible protocol versions and offers Repair.
- Bundle secret scan and resource allowlist.

**Required tests:**

- no Python installed;
- no repository checkout;
- fixed old port occupied;
- forged REST request;
- forged WebSocket connection;
- wrong, expired, replayed, and missing token;
- malicious browser origin;
- oversized and invalid events;
- mismatched UI/core protocol;
- missing packaged resource;
- antivirus-enabled smoke VM.

**Exit gates:**

- Packaged core starts without a terminal.
- React connects only after validated READY.
- Unauthorized local requests cannot invoke capabilities.
- The bundle contains no user data, .env file, credential, or test database.

### Phase 3 - Tauri Supervisor and Desktop Lifecycle

**Estimate:** 2-3 weeks

**Depends on:** Phase 2

**Objective:** Make Tauri the reliable owner of the complete application.

**Deliverables:**

- Rust supervisor state machine:
  - STOPPED;
  - STARTING;
  - MIGRATING;
  - READY;
  - DEGRADED;
  - CRASHED;
  - SAFE_MODE;
  - STOPPING;
  - RECOVERY_REQUIRED.
- Windows Job Object or equivalent owned-process-tree mechanism.
- Exact executable identity and PID validation.
- Graceful shutdown with bounded exact-process fallback.
- Backend parent-death monitoring.
- Three-crash bounded restart policy with stable-ready reset.
- Single-instance enforcement and second-launch focus.
- Safe mode that disables plugins, MCP, background voice, Telegram, WhatsApp,
  schedulers, and startup automation while preserving chat, settings, export,
  diagnostics, repair, and update.
- Custom accessible titlebar.
- Minimize, maximize/restore, and close behavior.
- System tray:
  - Open Maya;
  - Start/Stop Listening;
  - Pause Automation;
  - Diagnostics;
  - Check for Updates;
  - Quit.
- Startup, migration, degraded, safe-mode, and recovery UI.
- Owned optional-service registry with PID, identity, version, start time, and
  feature owner.

**Required tests:**

- double launch;
- backend crash loop;
- parent forced exit;
- Quit during idle, voice, tool execution, and optional-service activity;
- recycled PID simulation;
- optional child crash;
- database lock contention;
- safe-mode restart;
- no image-wide process termination.

**Exit gates:**

- One app launch creates one owned process tree.
- Quit leaves no Maya-owned process.
- User applications remain untouched.
- Repeated core failure reaches a usable recovery screen.

### Phase 4 - Voice Correctness and Channel Parity

**Estimate:** 2-3 weeks

**Depends on:** Phases 2-3

**Objective:** Make the existing turn-based voice path correct before adding a
realtime provider.

**Deliverables:**

- One VoiceSessionCoordinator and microphone lease.
- React/Tauri foreground session is the only normal desktop microphone owner.
- Native Python microphone capture is disabled in foreground desktop mode.
- Background wake-word mode is separately enabled, visible, and mutually
  exclusive with foreground capture.
- One channel-neutral TurnCoordinator owns:
  - session identity;
  - active turn;
  - cancellation;
  - approval;
  - progress;
  - timeout;
  - background completion;
  - final result;
  - control signals.
- Telegram, WebSocket, and native voice become adapters over the same turn state.
- Voice handles TurnResult mode and system-state signals instead of discarding
  them.
- Spoken Yes/No resolves the exact pending approval.
- Spoken status questions do not cancel the active task.
- Long tasks have a soft progress threshold and bounded hard timeout.
- Completion can be spoken after a background task finishes.
- Speaking-start fires when playable audio is scheduled.
- Audio-ended fires only after every scheduled source actually ends.
- Barge-in cancels:
  - model generation;
  - tool call when safely cancellable;
  - TTS request;
  - queued audio;
  - active playback;
  - stale completion events.
- Interrupted speech becomes the next user turn without freezing the session.
- Maya output cannot become a phantom user utterance.
- TTS provider selection, including Edge, is persisted truthfully.
- Provider fallback is visible in diagnostics.
- Raw voice transcripts are removed from normal logs.

**Channel parity contract:**

| Behavior | Telegram | Desktop text | Turn-based voice | Realtime voice |
|---|---|---|---|---|
| Shared tools and verifier | Required | Required | Required | Required |
| Exact approval | Button/text | Card | Spoken/card | Spoken/card |
| Progress | Message | UI | Spoken/UI | Spoken/UI |
| Cancel | Command | Button/new turn | Speech/button | Barge-in/speech/button |
| Background completion | Message | UI | Spoken/UI | Spoken/UI |
| Control signals | Channel adapter | Channel adapter | Channel adapter | Channel adapter |
| Session isolation | Required | Required | Required | Required |

**Required tests:**

- duplicate microphone ownership;
- phantom silence;
- speaker echo;
- speaking event ordering;
- audio completion timing;
- interruption during thinking, TTS, playback, approval, and tool execution;
- stale audio after cancellation;
- spoken approve/deny binding and expiry;
- status request during long task;
- provider failure and single fallback response;
- English, Banglish, Hindilish, and supported native-language speech;
- microphone permission denial and device disconnect.

**Exit gates:**

- No duplicate capture or reply.
- Interruption stops audible output quickly and leaves the session usable.
- Voice, Telegram, and text enforce the same execution policy.
- Approval and task completion are truthful and observable.

### Phase 5 - Gemini Live JARVIS-Style Realtime Voice

**Estimate:** 2-4 weeks

**Depends on:** Phase 4

**Objective:** Replace sentence-level pseudo-streaming with a true bidirectional
audio session while preserving Maya safety and tools.

**Architecture:**

    Microphone PCM
       -> VoiceSessionCoordinator
       -> RealtimeVoiceProvider
       -> Gemini Live session
       -> TurnCoordinator
       -> shared ToolBroker, permission, approval, and verifier
       -> streaming PCM output
       -> interruptible speaker queue

**Deliverables:**

- RealtimeVoiceProvider interface.
- GeminiLiveProvider using the official async Live connection.
- Provider lifecycle:
  - connect;
  - configure;
  - send audio;
  - receive audio and transcripts;
  - receive tool calls;
  - send tool results;
  - interrupt;
  - resume or reconnect;
  - close.
- Binary or equivalently bounded low-overhead audio transport.
- Continuous PCM input and output.
- Server-side VAD and turn detection.
- Immediate handling of server interruption events.
- Input and output transcript events for UI accessibility, without persistent
  raw transcript logging.
- Live tool calls route only through the shared ToolBroker.
- Tool cancellation messages are honored where cancellation is safe.
- Persistent voice context per foreground conversation.
- Session resumption after short network interruption.
- Context-window compression policy.
- Turn-based STT/text/TTS fallback with strict duplicate-response suppression.
- Cost, duration, and reconnect limits.
- Visible cloud-audio disclosure and session indicator.
- Local wake word as an opt-in mode after foreground realtime passes.
- Provider abstraction compatible with a future OpenAI Realtime or local
  provider without changing permissions or tools.

**Performance targets on a defined reference PC and network:**

- local playback stop after detected barge-in: target under 250 ms;
- first audible response p50: target under 1.5 seconds;
- first audible response p95: target under 3 seconds;
- no duplicated tool call or spoken reply after reconnect;
- no session freeze after interruption;
- no unbounded audio queue growth.

**Required tests:**

- synthetic realtime audio contract;
- real microphone and speaker loop;
- packet delay, loss, reconnect, and provider timeout;
- interruption while model speaks;
- interruption during tool call;
- approval dialogue;
- fallback without duplicate speech;
- wake-word false positive and lock behavior;
- long session context;
- device change;
- privacy and cost-limit enforcement.

**Exit gates:**

- Realtime voice uses an actual bidirectional provider session.
- All tool execution still passes through Maya policy.
- Network or provider failure returns to a usable fallback.
- The experience meets agreed latency and interruption targets.

### Phase 6 - Desktop UX, Feature Readiness, and Optional Components

**Estimate:** 2-3 weeks

**Depends on:** Phases 1-5

**Objective:** Make every feature discoverable, configurable, and truthful on a
clean machine.

**Deliverables:**

- Resumable first-run onboarding:
  - supported Windows and WebView2 check;
  - local/cloud privacy explanation;
  - language and style;
  - AI provider validation;
  - microphone disclosure and test;
  - permissions with safe defaults;
  - optional component choices and exact sizes;
  - optional Telegram and WhatsApp setup;
  - self-test and readiness summary.
- Capability dashboard using the standard readiness states.
- Stable feature identifiers and a LocalOpenAccessProvider that allows every
  shipped Desktop 1.0 feature without an account or network check.
- Diagnostics page with app, core, protocol, DB, voice, provider, component,
  disk, update, and service health.
- Signed component-manifest schema.
- Component manager with resumable download, size/hash/signature validation,
  compatibility, atomic publish, repair, and removal.
- Optional packs:
  - WhatsApp Node runtime and compatible browser;
  - local Whisper model assets;
  - Playwright browser;
  - local voice runtime;
  - approved media runtime.
- Base application remains useful when every optional pack is absent.
- Real-service qualification workflows for Telegram, WhatsApp, and email using
  explicitly approved accounts and recipients.
- Clear offline and degraded-state UI.

**Exit gates:**

- Every advertised feature has a truthful readiness state.
- Missing or corrupt optional components do not crash core chat.
- All installed packs pass signature, hash, version, and license validation.
- External-account features cannot claim live success without acknowledgment.

### Phase 7 - Installer, Signing, and Clean-Machine Qualification

**Estimate:** 2-3 weeks

**Depends on:** Phases 2-6

**Objective:** Ship a normal, trusted Windows installation.

**Deliverables:**

- Per-user Tauri NSIS installer.
- Product icon, publisher, version, legal, privacy, and support metadata.
- WebView2 bootstrap policy.
- Authenticode certificate and controlled signing workflow.
- Signed Tauri host, core, native binaries, optional launchers, and installer.
- SBOM and third-party notices.
- Artifact secret and malware scans.
- Repair installation.
- Explicit uninstall choices:
  - preserve user data;
  - remove user data after separate confirmation.
- Clean Windows 10 and 11 VM matrix.
- Standard non-admin installation.
- Install paths containing Unicode and spaces.
- Offline startup and missing-component behavior.
- Antivirus-enabled installation and launch.

**Exit gates:**

- Base app installs and launches without developer dependencies.
- Signatures validate on clean supported Windows.
- Repair restores application files without damaging user data.
- Default uninstall preserves user data.
- Artifact archive contains hashes, SBOM, notices, and verification evidence.

### Phase 8 - Signed Updater, Safe Restart, and Recovery

**Estimate:** 2-3 weeks

**Depends on:** Phase 7

**Objective:** Deliver secure atomic updates without corrupting active work or
user data.

**Deliverables:**

- Tauri updater and controlled process relaunch integration.
- Internal, beta, and stable feeds.
- Embedded updater public key.
- CI-protected private update-signing key.
- Signed versioned update manifest containing:
  - app/core version;
  - API protocol;
  - DB compatibility;
  - minimum source version;
  - artifact URL, size, and hash;
  - release channel;
  - rollout percentage;
  - security-critical flag.
- Update state machine:
  - IDLE;
  - CHECKING;
  - AVAILABLE;
  - DOWNLOADING;
  - VERIFYING;
  - READY_TO_INSTALL;
  - WAITING_FOR_SAFE_RESTART;
  - INSTALLING;
  - POST_UPDATE_HEALTH_CHECK;
  - COMPLETE;
  - RECOVERY_REQUIRED.
- Safe-restart gate for active:
  - voice session;
  - approval;
  - destructive tool;
  - file migration;
  - message/email delivery;
  - database migration;
  - component publication.
- Verified pre-migration database backup.
- Post-update pending marker.
- Host, core READY, DB open, protocol, and UI connection health checks.
- Recovery UI:
  - retry;
  - repair;
  - reinstall current;
  - download prior compatible installer;
  - restore verified backup where safe;
  - export data;
  - open redacted logs.
- Anti-downgrade rules.
- Staged internal, beta, and stable promotion.
- Signing-key rotation, revocation, and emergency-release runbooks.

**Required tests:**

- N-1 to N;
- interrupted download;
- offline check;
- invalid signature;
- modified artifact;
- insufficient disk;
- active-operation deferral;
- core startup failure;
- UI/core protocol mismatch;
- migration failure;
- irreversible migration recovery policy;
- beta-to-stable channel switch;
- update with no account or subscription.

**Exit gates:**

- A signed N-1 installation updates to N without data loss.
- Tampered update metadata or artifacts are rejected.
- Failed health check reaches recovery instead of looping.
- Security updates remain independent of commercial state.

### Phase 9 - Closed Beta and Stable Operations

**Estimate:** 2-4 weeks, driven by evidence

**Depends on:** Phases 0-8

**Objective:** Prove the complete product outside developer machines.

**Deliverables:**

- Controlled internal and closed-beta cohorts.
- Opt-in, privacy-reviewed health metrics containing no user content.
- Bounded rotating structured host/core logs.
- Redacted support bundle with preview and confirmation.
- Startup, crash, migration, update, voice, and component reliability dashboard.
- Incident response, release, rollback, support, privacy, and security-update
  policies.
- Known-limitations document.
- Stable cohort promotion plan.
- Emergency release rehearsal.

**Quality targets:**

- cold shell visibility under 2 seconds on the reference PC;
- cold core READY under 8 seconds without component download;
- warm core READY under 4 seconds;
- clean shutdown under 5 seconds before exact-process fallback;
- beta crash-free session rate at least 99.5 percent;
- stable target at least 99.9 percent after hardening;
- update success at least 99 percent on the supported matrix;
- zero known critical or high release-blocking security defects.

**Exit gates:**

- Beta thresholds hold for the agreed observation window.
- No release-blocking defect remains.
- Stable checklist and release evidence are approved.
- Signed stable artifacts and recovery materials are archived.

---

## 10. Future Subscription-Ready Boundary

Subscription code is not part of Desktop 1.0. The desktop must nevertheless
avoid architecture that would mix future commercial access with safety.

### 10.1 Capability Decision Model

Every feature decision must remain a composition:

    Effective Feature Access
      = Build Availability
      AND Future Entitlement
      AND User Permission
      AND Runtime Readiness
      AND Per-Action Approval When Required

For Desktop 1.0:

- Build Availability is available for every shipped feature.
- Future Entitlement is implemented by LocalOpenAccessProvider and always allows
  shipped features.
- No account or network call is required for this decision.

Stable feature identifiers and the access-decision interface should be created
only while the capability catalog is centralized. Do not add billing tables,
license checks, trial logic, or remote feature flags.

### 10.2 Safety Separation

A future paid plan:

- cannot enable a Windows permission;
- cannot approve a dangerous action;
- cannot disable audit logging;
- cannot bypass protected paths or process ownership;
- cannot grant administrator rights;
- cannot block security updates;
- cannot block export or access to local user data after expiry.

### 10.3 Future Cloud Control Plane

If separately approved later:

    Identity Provider
      + Billing Provider
      -> Signature-Verified Idempotent Webhooks
      -> Subscription State
      -> Entitlement Service
      -> Signed Short-Lived Entitlement Document
      -> Desktop Entitlement Provider

Future work must define:

- account identity;
- plans and feature policy;
- merchant and tax responsibility;
- webhook idempotency;
- entitlement signing and key rotation;
- offline grace;
- renewal, cancellation, refund, chargeback, and expiry;
- visible device management;
- clock rollback and replay defense;
- account export and deletion;
- support during billing outage.

Private local memory, contacts, messages, files, voice recordings, credentials,
and audit content must remain outside the minimum subscription data model.

### 10.4 Permanent Update Rule

Application and security updates are never conditional on:

- login state;
- trial state;
- subscription state;
- payment failure;
- entitlement service availability.

---

## 11. Update and Compatibility Contract

### 11.1 Atomic Base Release

The following update as one tested release:

- Tauri host;
- React UI;
- Python core;
- built-in prompts, skills, and resources;
- API protocol compatibility metadata.

Do not replace arbitrary Python files in production.

### 11.2 Independent Components

Optional packs have separate signed manifests but must declare:

- component ID and version;
- compatible app/core/protocol range;
- size;
- hash;
- signature;
- license;
- architecture;
- install and removal actions;
- health probe;
- rollback version.

### 11.3 Database Compatibility

- Schema versions increase monotonically.
- The release manifest declares supported source schemas.
- Every migration is applied once under a lock.
- Backup and integrity validation occur before user traffic.
- Automatic database downgrade is forbidden.
- At least one prior compatible installer remains available.

---

## 12. CI/CD and Supply Chain

### 12.1 Pull Request Gates

- Python compile/static checks used by the project.
- Complete deterministic Python tests.
- Focused security tests.
- Frontend TypeScript production build.
- Frontend unit and voice-state tests.
- Rust format, lint, and tests.
- Node syntax and service tests.
- Secret scan.
- Dependency vulnerability scan.
- License policy.
- Tauri capability/CSP validation.
- PyInstaller smoke build for packaging-sensitive changes.
- Markdown link and roadmap/backlog consistency check.

### 12.2 Nightly Gates

- Packaged core launch.
- Tauri debug bundle.
- synthetic voice contract;
- database migration matrix;
- optional component manifest validation;
- update feed validation;
- Windows 10 and Windows 11 smoke VMs;
- offline and degraded-state tests.

### 12.3 Release Pipeline

1. Validate tag, version manifest, changelog, and source cleanliness.
2. Run the complete release matrix.
3. Build React.
4. Build maya-core onedir.
5. Build optional components selected for the release.
6. Generate SBOM and notices.
7. Scan secrets, dependencies, and artifacts.
8. Authenticode-sign executables.
9. Build and sign NSIS installer.
10. Generate and Tauri-sign update artifacts.
11. Verify all signatures and hashes.
12. Publish immutable versioned artifacts.
13. Install on clean VMs.
14. Run post-publish smoke and update tests.
15. Publish the approved channel manifest.
16. Promote through cohorts.
17. Archive provenance and approvals.

Each release retains:

- source commit;
- workflow identity;
- toolchain versions;
- lock files;
- SBOM;
- notices;
- hashes;
- signature verification;
- malware scan;
- test, migration, installer, and update reports;
- release approver record.

---

## 13. Release-Blocking Test Matrix

### 13.1 Test Layers

| Layer | Required evidence |
|---|---|
| Unit | policy, parser, state, migration, access, supervisor, and audio scheduling |
| Contract | Tauri/core READY, auth, version, WebSocket, turn, voice, and component protocols |
| Integration | packaged core, temp LocalAppData, real SQLite, optional-service lifecycle |
| Desktop E2E | window, tray, sidecar, approvals, voice, Canvas, settings, and diagnostics |
| Capability | every row in the capability qualification matrix |
| Installer | install, upgrade, repair, uninstall, data preservation |
| Update | valid, invalid, interrupted, deferred, failed-health, and recovery |
| Security | local API, origin, CSP, tampering, path, process, secret, and approval |
| Reliability | crash, network loss, provider failure, power interruption, low disk |

### 13.2 Clean Machine Matrix

- Windows 10 22H2 x64.
- Current supported Windows 11 x64.
- Standard non-admin account.
- No Python, Node.js, npm, Rust, or Cargo.
- No previous Maya data.
- Supported prior Maya data.
- Unicode username.
- Install and data paths with spaces.
- Offline startup.
- Slow and intermittent network.
- Antivirus enabled.
- Low disk space.
- Old fixed port occupied.
- Missing and corrupt optional components.
- Microphone unavailable or permission denied.

### 13.3 Absolute Release Blocks

Do not ship stable when:

- installer requires a developer dependency;
- unauthenticated local requests can invoke capabilities;
- two Maya microphone pipelines can run;
- interruption leaves stale audio or a frozen voice session;
- a crash or Quit leaves an owned process;
- migration lacks backup and recovery evidence;
- uninstall removes user data by default;
- a secret, transcript, or private content appears in logs or artifacts;
- update signature rejection is untested;
- a tampered sidecar or component can run;
- clean Windows installation fails;
- an advertised capability falsely reports success;
- a critical or high security defect remains.

---

## 14. Prioritized Remaining Backlog

| ID | Priority | Work item | Depends on |
|---|---|---|---|
| ARCH-001 | P0 | Approve desktop ADR set | none |
| ARCH-002 | P0 | Create shared release and compatibility manifest | ARCH-001 |
| CI-001 | P0 | Add Windows pull-request baseline | ARCH-002 |
| DATA-001 | P0 | Resolve and pass all Windows runtime directories | ARCH-001 |
| DATA-002 | P0 | Add legacy-location migration and receipt | DATA-001 |
| DATA-003 | P0 | Add numbered DB migrations, lock, backup, and integrity gate | DATA-001 |
| SEC-001 | P0 | Add Windows-protected secret adapter and verified migration | DATA-001 |
| CORE-001 | P0 | Build PyInstaller onedir core and resource manifest | ARCH-002 |
| IPC-001 | P0 | Add dynamic port, token, READY, and version handshake | CORE-001 |
| IPC-002 | P0 | Authenticate REST and WebSocket clients | IPC-001 |
| HOST-001 | P0 | Build Rust supervisor and Windows Job Object | IPC-001 |
| HOST-002 | P0 | Add exact shutdown, parent death, and bounded restart | HOST-001 |
| HOST-003 | P0 | Add single instance and safe mode | HOST-001 |
| UX-001 | P1 | Add titlebar, tray, lifecycle, degraded, and recovery UI | HOST-001 |
| VOICE-001 | P0 | Add microphone lease and foreground/native ownership modes | HOST-001 |
| TURN-001 | P0 | Create shared TurnCoordinator and channel adapters | IPC-002 |
| VOICE-002 | P0 | Add spoken approval, progress, timeout, and control-signal parity | VOICE-001, TURN-001 |
| VOICE-003 | P0 | Correct speaking-start, audio-ended, and complete barge-in | VOICE-001 |
| VOICE-004 | P0 | Remove raw transcript logging and expose truthful fallback | VOICE-002 |
| LIVE-001 | P0 | Define RealtimeVoiceProvider | TURN-001 |
| LIVE-002 | P0 | Implement Gemini Live PCM session and tool broker bridge | LIVE-001, VOICE-003 |
| LIVE-003 | P0 | Add resumption, fallback, duplicate suppression, and cost limits | LIVE-002 |
| LIVE-004 | P1 | Add explicit opt-in local wake-word mode | LIVE-003 |
| CAP-001 | P0 | Centralize capability readiness and self-test report | ARCH-002 |
| PACK-001 | P1 | Define signed component manifest and manager | CAP-001 |
| PACK-002 | P1 | Package and qualify WhatsApp runtime | PACK-001 |
| PACK-003 | P1 | Package browser, STT, voice, and media components | PACK-001 |
| QUAL-001 | P0 | Qualify every capability in the matrix | CAP-001, PACK-001 |
| UX-002 | P1 | Add resumable onboarding and diagnostics | CAP-001 |
| REL-001 | P0 | Configure per-user NSIS installer | HOST-002 |
| REL-002 | P0 | Add Authenticode workflow, SBOM, notices, and scans | REL-001 |
| REL-003 | P0 | Add clean Windows installer, repair, and uninstall tests | REL-001 |
| UPD-001 | P0 | Add signed internal/beta/stable updater | REL-002 |
| UPD-002 | P0 | Add safe-restart and post-update health gate | UPD-001 |
| UPD-003 | P0 | Add recovery, compatible rollback, and backup restore workflow | UPD-002 |
| OPS-001 | P1 | Add structured redacted host/core logs | HOST-001 |
| OPS-002 | P1 | Add redacted support bundle and incident runbooks | OPS-001 |
| BETA-001 | P0 | Complete closed beta and stable qualification | all other P0/P1 items |
| COMM-001 | P1 | Add LocalOpenAccess feature-boundary interface | ARCH-002, CAP-001 |
| COMM-002 | DEFERRED | Design identity and entitlement service | separate future approval |
| COMM-003 | DEFERRED | Select and integrate billing provider | COMM-002 and separate approval |

P0 and P1 are required before Stable Desktop 1.0. P0 marks critical-path or
release-blocking work; P1 marks required product-completion work that can often
run in parallel. COMM-001 is boundary hygiene only and must not introduce an
account, paywall, or network entitlement check. DEFERRED items are outside
Desktop 1.0 and require separate approval.

---

## 15. Critical Path and Planning Range

Critical path:

    Architecture
      -> Runtime Data and Secrets
      -> Packaged Core and Secure IPC
      -> Tauri Supervisor
      -> Voice Correctness
      -> Realtime Voice
      -> Capability Qualification
      -> Installer and Signing
      -> Updater and Recovery
      -> Closed Beta
      -> Stable

For one experienced full-time engineer with review support, the remaining plan is
approximately 16-24 engineering weeks plus the evidence-driven beta window.
This is a planning range, not a delivery promise.

Parallel work can reduce calendar time for:

- CI and test infrastructure;
- Windows packaging;
- UI lifecycle work;
- signing and release operations;
- optional component licensing;
- clean-VM qualification.

External prerequisites that must be tracked separately:

- Authenticode certificate or signing service;
- protected CI secret storage;
- Windows 10/11 clean VM capacity;
- controlled HTTPS release/update hosting;
- approved Gmail and WhatsApp live-test accounts and recipients;
- redistribution and license approval for optional binaries and models.

---

## 16. First Execution Sprint

**Length:** 2 weeks

**Objective:** Prove that Tauri can launch one versioned packaged core with
production paths and a secure readiness contract.

### Sprint Tasks

1. Approve ADR-001 through ADR-005.
2. Add the shared release/version manifest.
3. Add Windows CI for current deterministic, frontend, Node, and Rust checks.
4. Implement Tauri runtime-path resolution.
5. Expand backend runtime overrides for cache, logs, backup, and temp.
6. Create the first PyInstaller onedir spec and smoke build.
7. Implement dynamic port and non-secret READY event.
8. Implement the per-launch token and authenticated health probe.
9. Launch the packaged core from a minimal Rust supervisor.
10. Stop it gracefully and verify no owned process remains.
11. Record failures and evidence in the backlog.

### Sprint Demo

A tester starts Maya through Tauri, observes:

- one application instance;
- one packaged core;
- production-style per-user paths;
- dynamic authenticated connection;
- validated READY versions;
- one successful local text turn;
- graceful Quit;
- no remaining Maya-owned process.

Do not begin updater, billing, or optional-pack publication before this bootstrap
contract passes.

---

## 17. Definition of Done for Stable Desktop 1.0

Desktop 1.0 is DONE only when:

- a signed clean-machine installer works without developer tools;
- Tauri owns one authenticated, version-compatible core and process tree;
- runtime state and secrets live outside the installation directory;
- supported legacy data migrates with backup and recovery;
- one database writer and one microphone owner exist;
- every capability has a truthful readiness state and qualification record;
- all installed and configured features pass their packaged acceptance flows;
- dangerous approvals remain exact, expiring, and non-replayable;
- turn-based and realtime voice interruption, approval, progress, and completion
  are reliable;
- Gemini Live or the selected realtime provider passes latency, fallback, and
  privacy gates;
- tray Quit removes every Maya-owned process;
- repair and uninstall behavior is verified;
- user data is preserved unless separately confirmed for removal;
- app, core, installer, and update artifacts have valid signatures;
- N-1 to N signed update succeeds without data loss;
- invalid or modified updates are rejected;
- failed startup or update reaches a recovery path;
- optional components are signed, isolated, repairable, and truthful;
- logs and support bundles contain no secrets or private content;
- SBOM, notices, privacy policy, support docs, and runbooks ship;
- stable release gates pass on supported Windows 10 and 11;
- no account, billing, trial, paywall, or subscription is required;
- future entitlement integration can be added without rewriting permissions,
  approvals, storage, startup, or updates.

---

## 18. Long-Term Product Rule

Maya is an industry-grade desktop product when installation, daily use, voice,
automation, updates, recovery, and support feel like one application instead of
separate development services.

Future features may extend the product, but they must preserve:

- exact lifecycle ownership;
- user data control;
- truthful feature readiness;
- permission and approval boundaries;
- signed updates;
- recoverability;
- subscription-independent security and local data access.
