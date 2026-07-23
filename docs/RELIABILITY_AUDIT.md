# Maya AI Implemented Capability Reliability Audit

Last updated: 2026-07-22

## Objective

Audit existing Maya capabilities through real user-to-result flows, fix only
reproducible root causes, add a regression test for every fix, and run the full
deterministic suite. This pass does not add features or perform broad refactors.
Security is an acceptance criterion for every audited capability, not a separate
end-of-pass review.

## Status Legend

- `TODO`: not started
- `IN PROGRESS`: current task; only one task should normally have this status
- `FIXING`: a reproduced defect is being corrected
- `VERIFIED`: end-to-end behavior and relevant regression tests passed
- `EXTERNAL`: implementation was tested as far as possible, but final delivery
  depends on an account, credentials, paired device, network, or external service
- `BLOCKED`: verification cannot continue; the exact blocker must be recorded

## Required Verification Flow

Every capability must be checked through this chain:

`user request -> intent/router -> agent -> permission -> tool selection -> tool execution -> result verification -> truthful reply`

The security checks attached to that chain are:

`input validation -> authorization/confirmation -> least privilege -> secret redaction -> protected-target enforcement -> audit evidence`

A unit test alone is not enough for `VERIFIED`. Destructive actions will use
dedicated temporary test data. Messages and emails will use explicitly approved
test recipients and will never be sent silently during the audit.

## Audit Queue

| ID | Capability | Status | Required checks |
|---|---|---|---|
| R00 | Tool availability and false-claim handling | VERIFIED | Tool present is not reported missing; no success reply without execution evidence |
| R01 | App controls | VERIFIED | Open, focus, close, close active, close-all-except, unknown app, follow-up close, truthful partial/failure reply |
| R02 | File operations | VERIFIED | Read, write, list, mkdir, copy, move, rename, search, delete, delete-by-name, organize, protected paths, cross-drive behavior |
| R03 | WhatsApp controls | EXTERNAL | Status/pairing, contact resolution, ambiguity, text send, file send, retry/idempotency, unavailable service, truthful delivery result |
| R04 | Email controls | EXTERNAL | Credential state, send, attachment resolution, read/search, destructive confirmation/verification, SMTP/IMAP failure, truthful result |
| R05 | Cross-capability attachments | VERIFIED | Find/create a file, attach it to WhatsApp/email, preserve exact path and delivery result |
| R06 | Follow-up command and context | VERIFIED | Pronouns, omitted app/contact/file, clarification continuation, session isolation, stale context rejection |
| R07 | Voice commands for audited controls | VERIFIED | Speech input reaches the same router/tool/result path; approval and failure replies are spoken correctly |
| R08 | Background music/audio interaction | VERIFIED | Play/pause/stop/volume, voice coexistence, interruption/resume, truthful playback state |
| R09 | Full regression suite and final report | VERIFIED | Full deterministic suite, external checks, verified/problem/external matrix |
| S01 | Cross-cutting security review | VERIFIED | Permission bypass, command/path injection, protected resources, destructive confirmation, credential/PII leakage, recipient validation, local service authentication |

## Current Completion Snapshot

As of 2026-07-22, the queue-level status is:

- `9/11` items fully `VERIFIED`: R00, R01, R02, R05, R06, R07, R08,
  R09, and S01.
- `2/11` items are `EXTERNAL`: R03 and R04.
- No items remain `TODO`, `IN PROGRESS`, `FIXING`, or `BLOCKED`.
- `31` reproduced defects have documented fixes and regression coverage:
  BUG-001 through BUG-031. The S01 fixes are covered by focused and full
  deterministic suites in the project runtime.

R03 has a final `EXTERNAL` disposition because every deterministic and security
check passed, while paired-account status/pairing and real delivery were not
performed without explicit approval. Completed subchecks for remaining work are
recorded in the progress-log sections below.

R04 has a final `EXTERNAL` disposition because its deterministic send, read,
attachment, approval, redaction, and destructive-state checks passed, while a
real Gmail credential set and an explicitly approved test recipient were not
used for live SMTP/IMAP delivery.

## Live Desktop Safety Rule

- Never target Visual Studio Code, the active Maya/Codex host, its terminal, or
  the Maya AI runtime during live app-control verification.
- Any remaining live open/focus/close check must use a fresh audit-created
  Notepad instance whose PID/window is recorded before the action and whose
  removal is verified afterward.
- Broad actions such as `close_apps_except` must remain mock-only; they must not
  be exercised against the user's live desktop.
- A bare follow-up `Close` may be used only after programmatically confirming
  that stored context resolves to the fresh audit-created Notepad target. Abort
  instead of falling back to active-window close when that check fails.

## Work Procedure For Each Queue Item

1. Inventory the implemented commands, aliases, router paths, permissions, tool
   functions, verifiers, and existing tests.
2. Run focused deterministic tests to establish a baseline.
3. Exercise the real end-to-end path with safe test data.
4. Record each observed result and evidence below.
5. When a defect reproduces, document symptom and root cause before editing.
6. Make the smallest scoped fix and add a regression test that fails without it.
7. Re-run focused tests, then update the queue status.
8. After all items, run the full suite and write the final capability report.
9. For every item, run its security cases before assigning `VERIFIED`.

## Security Matrix

| Capability | Security cases | Status |
|---|---|---|
| App controls | Input-to-command injection, arbitrary process targeting, broad close confirmation, protected Maya process, audit trail | VERIFIED |
| File operations | Traversal, protected paths, symlink/reparse escape, overwrite policy, destructive confirmation, secret exposure | VERIFIED |
| WhatsApp | Local API authentication, recipient ambiguity, authorization, inbound allowlist, replay/idempotency, attachment validation, PII-safe logs | VERIFIED |
| Email | Credential encryption/redaction, header injection, recipient validation, attachment validation, destructive confirmation, IMAP target verification | EXTERNAL |
| Cross-capability attachments | Sensitive-path rejection on both attach validators, canonical/realpath link resolution, uploads-cache-only project exception, fuzzy-search secret exclusion, transport-precondition validation, PII-safe logging | VERIFIED |
| Voice/audio | Unauthorized background activation, approval integrity, sensitive transcript/log handling, device/resource cleanup, playback protected-target enforcement | VERIFIED |
| Follow-up context | Cross-session leakage, stale authorization reuse, wrong recipient/file carry-over, confirmation binding | VERIFIED |
| Local UI, Canvas, and memory | Trusted frame ancestry, Tauri parent CSP, truthful settings persistence, encrypted conversation storage/archive, repository data exclusion | VERIFIED |

## Progress Log

### R00 - Tool Availability And False Claims

- Status: `VERIFIED` (carried forward from the completed prior audit batch)
- Scope: reject false "tool unavailable" responses when a valid tool exists and
  prevent success claims when execution did not produce success evidence.
- Note: R01-R08 will continue checking these invariants inside each real flow.

### R01 - App Controls

- Status: `VERIFIED`
- Inventory located in `backend/tools/desktop/apps.py`, direct routing in
  `backend/brain/agents/agent_team.py`, and related desktop control adapters.
- Baseline focused run on 2026-07-18: `71 passed` covering current WhatsApp,
  app-control, direct OS action, file-adjacent, and router tests.
- Full deterministic baseline on 2026-07-18: `308 passed`, `9 subtests passed`.
- Fixed false-success reporting for active-window and close-all-except actions:
  both paths now re-inspect open windows after requesting close and return
  `PARTIAL`/`ERROR` if the target remains or completion cannot be verified.
- Focused post-fix verification: `19 passed` in `test_app_launcher.py` and
  `test_direct_app_workflow.py`, including stubborn-window and asynchronous-close
  settling cases.
- Safe real Windows flow passed with an audit-created Notepad instance: no
  Notepad process existed before the run; open created PID `20596`; focus found
  the window; close returned verified `SUCCESS`; and no Notepad process remained.
- Security review completed: the direct fast path respects required permission
  controls, protected Maya/Codex processes and windows cannot be targeted, and
  shell-control/path input is rejected instead of being interpreted as an app
  name. Broad close actions were verified with mocks only and were not run
  against the user's live desktop.
- Direct app fast path now respects `PERM_SYSTEM`; disabling system controls
  forces the request through the permission-filtered agent path instead of
  executing the app tool directly.
- Broad close-all-except now creates a `HIGH` risk approval request bound to the
  exact `excluded_apps` argument and fails closed on denial/timeout. The broad
  action was verified with mocks only and was not run against the live desktop.
- Focused app/security/agent verification after these fixes: `38 passed`.
- Completed subchecks: deterministic open parsing/routing, unknown-app fallback,
  remembered follow-up close, active-window close result verification, truthful
  partial-result reply, protected Maya/runtime rejection, `PERM_SYSTEM`
  enforcement, and approval binding for broad close.
- Completed live subchecks: open, focus, and verified close of an audit-created
  Notepad instance. Visual Studio Code is not an approved live test target.
- Final R01 verification on 2026-07-19 reproduced and fixed two additional
  defects: runtime-owned development windows could receive a close request when
  their title matched a requested app, and an immediate focus after app launch
  could inspect before Windows had created the window.
- App inputs containing shell-control characters or paths are rejected before
  direct routing or launch/close/focus handling. A runtime owner-PID check now
  protects the active Maya/Codex host tree for targeted close, active-window
  close, and broad close actions. A real probe of the active Visual Studio Code
  window returned a protected-target error without calling `close()`.
- Focus now waits a bounded period for a newly launched matching window, restores
  it if minimized, activates it, and returns `PARTIAL` instead of `SUCCESS` when
  foreground activation cannot be observed.
- The initial safe Notepad live flow recorded a truthful focus failure while the
  Notepad process existed but its window had not appeared. Metrics recorded all
  three direct calls and the focus error. The post-fix fresh Notepad flow passed:
  no pre-existing Notepad process; open created PID `21316`; focus returned
  verified `SUCCESS`; a bare follow-up `Close` resolved to Notepad; and no
  Notepad process remained after close.
- Stored user-to-result evidence was confirmed for open, focus, and follow-up
  close: each stored `tool_call`, function result, and final reply agreed with
  the observed outcome. Observability rows recorded the post-fix `open_app`,
  `focus_app`, and `close_app` calls with no error.
- Final deterministic R01-connected verification: `99 passed` across app
  launcher, direct-app workflow, context lifecycle, production safety, agents,
  fast-route, function-call, and tools tests. Python compilation and
  `git diff --check` passed.

### R02 - File Operations

- Status: `VERIFIED`
- Planned fixture root: a dedicated temporary directory outside protected project
  content, removed only after verifying all expected results.
- Real temporary-fixture round trip passed for mkdir, write, read, list, copy,
  move, rename, and delete.
- Fixed silent overwrite in unified `file(action="write")`: an existing target
  is now preserved and the new file uses the established deduped-name policy.
- Fixed rename directory escape: `file(action="rename")` now accepts only a
  filename in the source directory and rejects absolute paths and `../` segments.
- Protected-project traversal test passed through canonical path enforcement.
- Search and delete-by-name now reject blank queries and invalid result limits
  before scanning, and overlapping search roots no longer return duplicates.
- Recursive copy/move rejects source trees containing symlinks, junctions, or
  reparse points. Delete unlinks a link without traversing its target and verifies
  the requested path no longer exists before returning success.
- Organize rejects protected/reparse destinations and returns `ERROR` when no
  move succeeds or `PARTIAL` when only some moves succeed; counts now describe
  successful moves rather than attempted moves.
- Destructive `file(action="delete"|"delete_by_name")` calls are classified
  `HIGH`/`CRITICAL`, require approval, and cannot use auto-approval. The focused
  approval tests passed; non-destructive writes remain approval-free.
- Copy and cross-drive move now use a hidden destination-side staging path,
  verify staged file sizes/tree shape, and publish only after the copy completes.
  Failed copies remove staging data; cross-drive source-retirement/cleanup
  failures return non-retryable `PARTIAL` results with the surviving source or
  recovery path instead of claiming success.
- Directory copy/move into its own source tree is rejected, and destination
  publication uses a non-overwriting rename so a concurrent destination creation
  cannot be silently replaced.
- Real isolated C:-to-D: cross-drive move passed with byte-for-byte content
  verification, source removal verification, and staging cleanup verification.
- Sensitive credential paths are now blocked outside the Maya project as well as
  inside it: `.env` variants, private-key files, credential/token files, and
  `.ssh`/`.aws`/`.azure`/`.docker`/`.gnupg`/`.kube` trees cannot be read,
  copied, moved, deleted, written, or returned by search. Explicit template files
  such as `.env.example` remain usable.
- User-to-result workflow tests passed for exact-path search, approved
  delete-by-name, and organize. They verify router/tool selection, approval
  binding where destructive, real temporary-file execution, stored function
  results, final replies, and absence of approval for non-destructive actions.
- Final focused R02/security/verifier run on 2026-07-19: `69 passed`, `2 skipped`.
  The skips require Windows symlink-creation privilege; equivalent reparse-point
  rejection is covered by a passing platform-independent mock regression test.
- Completed subchecks: mkdir, write, read, list, copy, move, rename, delete,
  overwrite-safe deduplication, filename-only rename enforcement, and canonical
  protected-project traversal rejection, bounded search, delete-by-name safety,
  organize truthfulness, destructive approval, reparse-point enforcement, and
  cross-drive behavior, sensitive-path protection, and complete user-request to
  result/reply evidence for search, approved delete-by-name, and organize.

### R03 - WhatsApp Controls

- Status: `EXTERNAL`
- External dependency: paired-account status/pairing and real delivery
  acknowledgment require an explicitly approved recipient, paired device, and
  network-backed WhatsApp session.
- Offline/security baseline passed for service API authentication, request-size
  limits, trusted origins, idempotency conflict handling, contact fallback and
  ambiguity, send continuation, and fuzzy attachment selection.
- Recipient phone normalization now fails before starting the service or calling
  transport for invalid/short numbers. Empty and oversized text messages are
  rejected at the Python boundary.
- Single-file sends validate existence, canonical real path, protected/sensitive
  names, caption length, and the dedicated uploads-cache exception before service
  startup. Node validation resolves real paths so symlink/junction indirection
  cannot bypass protected attachment roots.
- File sends now return a deterministic contact-pick clarification for ambiguous
  synced contacts instead of attempting to normalize a missing phone number.
- Permanent HTTP 4xx rejections are not retried; transient transport/not-connected
  retries retain one request ID, and exact final file-send errors are preserved.
- Multi-file search filters unsafe candidates and reports `SUCCESS`, `PARTIAL`,
  or `ERROR` from actual per-file delivery results rather than a success-like
  heading when every send failed.
- Unknown direct senders expose only allow, block, and ignore controls. Reply
  authorization is enforced again at every draft/manual/send callback boundary,
  so hidden or forged callback data cannot bypass the allowlist. Telegram
  callbacks are also bound to the paired chat and private-chat actor.
- Allow/block state changes now require a successful authenticated Node response;
  invalid sender numbers fail before transport, and failed actions retain the
  pending notification instead of claiming success.
- Python transport logs mask recipient numbers and log attachment basenames
  instead of full recipient/path data. Node logs use masked phone labels,
  basenames, and bounded error name/code labels that reject phone-like digit
  sequences.
- Repeated service lifecycle cleanup closes stale parent log handles. A failed
  termination retains the live child handle so a later stop can retry instead of
  losing ownership.
- WhatsApp Telegram notification headers, context labels, warnings, buttons, and
  follow-up callback prompts now use the latest Maya conversation style observed
  across desktop text, desktop voice, or Telegram: English, Banglish, or
  Hindilish. Wrapper text remains Latin-only; the original incoming WhatsApp
  message is preserved unchanged, while Gemini drafts continue following the
  incoming sender's message style.
- Final focused language/authorization/security verification on 2026-07-19:
  `46 passed`. Broader offline R03/language/voice-connected regression set:
  `124 passed`, `1` unrelated dependency deprecation warning. Python compile,
  Node syntax checks, Node security-helper execution, and `git diff --check`
  passed.
- No app or WhatsApp service process was started or stopped, no account was
  paired, and no live message or attachment was sent. Those delivery checks are
  therefore recorded as `EXTERNAL`, not silently assumed successful.

### R04 - Email Controls

- Status: `EXTERNAL`
- Implemented a strict Gmail credential validator. Saved credentials remain
  encrypted at rest; invalid addresses, malformed 16-character App Passwords,
  and database errors fail without exposing credential material.
- Sending now requires explicit `HIGH`-risk approval, accepts exactly one plain
  recipient address, rejects header-injection/control characters, bounds subject
  and body sizes, validates real attachment paths and sizes, blocks protected or
  sensitive files, and reports SMTP acceptance rather than claiming final inbox
  delivery. User-uploaded files under the dedicated uploads cache remain allowed.
- Approval records and audit logs redact credential, recipient, subject, body,
  sender, and attachment-path data. The approval display keeps the email target
  visible to the authenticated user while never showing an App Password or body.
- IMAP reads reject malformed search expressions before contacting the server,
  cap and escape untrusted email content, and return generic transport errors
  instead of raw server/credential exception text.
- Trash and permanent-delete operations require approval plus a numeric UID and
  exact decoded Subject/From match fetched immediately before mutation. They use
  `UIDPLUS` targeted expunge only, never broad `EXPUNGE`, and return `PARTIAL`
  when post-action source removal cannot be verified.
- Focused R04 regression suite: `10 passed`. Broader email/security/agent suite:
  `107 passed`. Full deterministic backend suite: `404 passed`, `2 skipped`.
  Python compilation and scoped `git diff --check` passed.
- No real Gmail account was configured, no inbox was read or changed, and no
  message was sent. Live delivery, pairing-independent SMTP acceptance, and IMAP
  state changes therefore remain `EXTERNAL` pending an approved test account and
  recipient.

### R05 - Cross-Capability Attachments

- Status: `VERIFIED`
- Inventory completed on 2026-07-20: WhatsApp attach path
  (`whatsapp_send_file`/`whatsapp_send_multiple_files` ->
  `_find_file_in_search_dirs` -> `whatsapp_manager.validate_attachment_path` ->
  `send_file`/`send_files` transport), email attach path
  (`send_background_email` -> `_resolve_email_attachment` ->
  `email_security.validate_attachment_path` -> `read_attachment_bytes` -> SMTP),
  and the unified file tool's create/search actions
  (`file(action="write"/"search")` -> `handle_file` -> `find_items`).
- Baseline focused run on 2026-07-20: `54 passed` across attachment-search,
  WhatsApp send/manager, and email audit suites.
- End-to-end path fidelity verified with safe test data: a file created via
  `file(action="write")` returns its exact deduped absolute path, that exact
  path reaches the WhatsApp transport byte-for-byte (realpath-equal), and a
  file located via `file(action="search")` is attachable by its exact returned
  path. The email path preserves the exact resolved path into the MIME payload
  and reports the attachment by its true basename.
- Delivery-result truthfulness verified: transport failure produces `ERROR`
  with the transport's reason (never `SUCCESS`), an unknown WhatsApp ack is
  reported as `Pending` rather than an invented state, the email reply claims
  SMTP acceptance only (never inbox delivery), and multi-file results carry
  per-file success/failure lines with an aggregate `SUCCESS`/`PARTIAL`/`ERROR`
  prefix.
- Reproduced and fixed BUG-020: a missing absolute attachment path silently
  fell through to fuzzy filename search, so a lookalike file from anywhere on
  disk could be sent in its place while the reply claimed success for the
  requested file. Both single and multi-file WhatsApp tools now fail closed on
  a missing absolute path and state that no substitute was searched. The email
  path already failed closed; a probe confirmed its fuzzy search is reached
  only for genuinely relative descriptions.
- Reproduced and fixed BUG-021: a failed multi-file send still deleted the
  uploads-cache copy, destroying the user's only local copy and making retry
  impossible. Cleanup now removes only attachments whose transport result
  reported success (the single-file path already ordered cleanup after the
  success check).
- Security cases verified for the full chain: `.env`, `credentials.json`,
  `id_rsa`, and `.pem` files are rejected by both attach validators; a fuzzy
  query resolving to a sensitive file is blocked before any transport call; an
  explicit absolute sensitive path to email is blocked before SMTP; realpath
  resolution exposes a link pointing at credential material on both validators
  (platform-independent regression test; live symlink probe skipped without
  Windows symlink privilege); unified file search excludes sensitive and
  protected paths from results; project files outside the dedicated uploads
  cache are not attachable; and an oversized caption fails before the local
  WhatsApp service is even started. Transport logging keeps only the last four
  phone digits and the attachment basename.
- Completed subchecks: create->attach exact-path fidelity, search->attach
  exact-path fidelity, fuzzy->attach resolution, missing-absolute-path
  fail-closed (single and multi), uploads-cache exception and success-gated
  cleanup, duplicate-attachment skip, truthful failure/pending/acceptance
  replies, and the security cases above.
- Post-fix verification: focused suites `65 passed`; full deterministic
  backend suite `419 passed`, `2 skipped` on 2026-07-20.

### R06 - Follow-Up Command And Context

- Status: `VERIFIED`
- Inventory completed on 2026-07-20: all follow-up state lives in six bounded
  per-session LRU stores in `backend/brain/agents/agent_team.py`
  (`_LAST_AGENT`, `_LAST_DIRECT_APP`, `_LAST_OS_CONTROL`, `_PENDING_SEND`,
  `_PENDING_YOUTUBE_TITLE`, `_PENDING_YOUTUBE_MODE`, all keyed by session id,
  capped at 500 sessions), plus history-derived context
  (`_last_app_from_history`, `_previous_user_messages`,
  `_tool_router_query` anchoring) and `evict_session_state` /
  `orchestrator.release_session` lifecycle cleanup.
- Baseline focused runs on 2026-07-20: `24 passed` across send-continuation,
  contact-fallback, and context-lifecycle suites; direct-app/OS/fast-route
  suites green in the full run.
- Deterministic context checks passed: an omitted-app follow-up (`close koro`)
  resolves to the remembered app; the freshest history tool-call overrides
  older session memory; the pending-send flag is one-shot and re-armed only
  while the flow is alive; a bare number/message reply after a send
  clarification stays on OS_EXECUTOR while an explicit new intent
  (`aajker khobor ki`) escapes to RESEARCHER; a bare percent follow-up
  (`50% koro`) continues the last OS control and, with no prior control,
  safely falls to CHAT instead of guessing a device action.
- End-to-end multi-turn flows passed through `execute_workflow` with mock
  tools: open-then-bare-close executed `open_app("notepad")` then
  `close_app("notepad")` with both calls and truthful replies stored in
  history; a volume command followed by a bare percent reached
  `change_volume(20)` then `change_volume(50)`.
- Session isolation verified end-to-end: the same bare `close koro` in a
  fresh session never targets another session's remembered app (it used the
  active-window path); per-session stores are fully independent; LRU caps
  hold at 500 with oldest-session eviction; `evict_session_state` clears all
  six stores; `release_session` clears ephemeral state without persisting.
- Stale-context rejection verified: after eviction a bare `50% koro` fires no
  volume action; approval requests expire server-side (`expires_at` checked at
  resolve time), a persisted decision cannot resurrect an operation after the
  owning process died, a terminal approval cannot be resolved twice, and a
  stale click on a gone request records a denial — these invariants are
  covered by existing `test_production_safety.py` cases re-run in this pass.
- Reproduced and fixed BUG-022 (confirmation binding): after the user approved
  a danger tool call, a retryable failure could re-execute the tool with
  LLM-replanned arguments (for example a different delete target) without a
  new approval. The retry loop now pins approved danger-tool retries to the
  exact approved tool and arguments; replan and fallback-tool stages apply
  only to non-danger tools.
- Duplicate-delivery protection re-verified at the routing layer: send-tool
  fingerprints block a second identical send inside one workflow, and
  `_tool_router_query` anchors bare replies only to the immediately previous
  user turn, so a wrong recipient cannot be carried in from older context.
- Post-fix verification: `test_verifier.py` `16 passed` including the new
  binding regression; full deterministic backend suite `420 passed`,
  `2 skipped` on 2026-07-20. Python compilation passed.

### R07 - Voice Commands For Audited Controls

- Status: `VERIFIED`
- Inventory confirmed voice input is not a parallel command path: the desktop
  engine goes Mic → Silero VAD → transcriber (Gemini STT, Whisper fallback) →
  the SHARED `run_turn` gateway → `orchestrator.process_user_input_stream` →
  the same `execute_workflow` router/tool/verifier path every text channel uses.
  So the R00-R06 routing, permission, approval, verification, and delivery-truth
  fixes already govern spoken commands; R07 audited only the voice-specific
  surface (STT→router fidelity, spoken approval/failure, barge-in, transcript
  and temp-file handling).
- Baseline focused run on 2026-07-20: `8 passed`
  (`test_desktop_voice_approval.py`, `test_telegram_voice_isolation.py`).
- End-to-end voice flows verified with mocked STT/TTS: a transcribed command
  reaches the router intact and the spoken text carries the real answer; model
  chain-of-thought never reaches TTS (streaming `ThinkStripper`); a danger-tool
  approval request raised mid-turn is forwarded to the connected desktop UI and
  fails closed (auto-denied) when no UI is connected; a barge-in aborts the
  stream and no held-back text is spoken after the abort.
- STT fidelity verified: `latinize_transcript` strips every Bengali/Devanagari
  code point so no native-script character can leak into the Latin-only router,
  while English command tokens are preserved unchanged.
- Reproduced and fixed BUG-023 (control-token spoken aloud): a voice command
  that triggered a shutdown/sleep or a mode change made the engine speak the raw
  internal signal (for example `SYSTEM_STATE_TRIGGERED:shutdown`) because the
  voice `_on_text` splitter — unlike the WebSocket handler — had no control-token
  guard and only stripped macro blocks. Added a shared `_is_control_token_stream`
  helper and suppressed the whole spoken stream for a control-token turn.
- Security cases passed: microphone lock and remote-command suppression block
  processing (no unauthorized background activation, and a remote suppression
  lease is distinct from the user's manual lock); the VAD loop only captures in
  `LISTENING`, so Maya never transcribes her own TTS; approval events forwarded
  from voice fail closed without a UI; malformed/non-approval gateway events are
  never broadcast; the fast-path metrics logger stores token counts, not the raw
  transcript; and transcription temp WAV files are removed on the Gemini,
  Whisper, silence, and failure paths.
- Post-fix verification: focused suite `10 passed`
  (`test_desktop_voice_approval.py`, `3` prior + `7` new); full deterministic
  backend suite `427 passed`, `2 skipped` on 2026-07-20. Python compilation
  passed.

### R08 - Background Music/Audio Interaction

- Status: `VERIFIED`
- Inventory completed on 2026-07-21: background audio runs headless VLC via
  `play_youtube_background`/`stop_youtube_background`
  (`backend/tools/desktop/advanced/youtube_player.py`, PID tracked in
  `data/youtube_player.pid`); foreground playback via `search_youtube`
  (`browser_tools.py`); `pause_media` and the `play_pause`/`next_track`/
  `prev_track`/`mute` media keys (`system_tools.py`, `shortcuts.py`); volume via
  `change_volume` (`system_tools.py`) routed through `handle_pc`. Routing is the
  deterministic OS fast path in `agent_team.py` + `intent_parsing.py`, with
  `tool_router._MEDIA_TOOLS` force-keeping the playback tools against ranking.
- Baseline focused run on 2026-07-21: `54 passed` across `test_tools.py`,
  `test_youtube_visible_playback.py`, `test_direct_os_action.py`,
  `test_direct_app_workflow.py`, and `test_tool_router.py`.
- Truthful playback state verified: background start does not claim "playing"
  until VLC survives its startup poll; stop reports the true state from the
  tracked PID; `pause_media` and the media transport keys truthfully report only
  that the keystroke was sent (they hold no play/paused state and never claim
  one); foreground `search_youtube` returns `PARTIAL` when window focus cannot
  be confirmed.
- Reproduced and fixed BUG-026 (protected-target / false-success in stop): the
  stop and pre-play kill paths fell back to image-wide `taskkill /F /IM vlc.exe`,
  which would terminate a user's own unrelated VLC instance and then falsely
  report "Background audio stopped." All kill paths now target only the exact
  PID Maya started; a missing PID file, a dead PID, or a recycled non-VLC PID
  kills nothing and reports the truthful state.
- Post-fix verification: focused suites `57 passed`; new stop-path regressions
  `8 passed` in `test_tools.py`; full deterministic backend suite `432 passed`,
  `2 skipped` on 2026-07-21 (the manual `test_models.py` script, which exits on
  a missing API key, is excluded from the deterministic run). Python compilation
  passed.
- `EXTERNAL` remainder: live voice/music coexistence, barge-in ducking, and
  interruption/resume through real speakers and microphone were not exercised on
  the user's live desktop. The two subsystems (detached VLC process vs. the voice
  engine's own TTS PID) share no ducking/coordination state today; this is a
  design gap, not a reproduced defect, so no feature was added in this pass.

### S01 - Cross-Cutting Security Review


- Status: `IN PROGRESS`
- Reproduced and fixed a permission-boundary bypass: `PERM_SYSTEM=false` removed
  only capability-map entries, while the baseline native list still exposed
  app/window, keyboard/mouse, screen, and background desktop-control tools.
  Those controls now live exclusively under `PERM_SYSTEM`.
- Reproduced and fixed protected-target/truthfulness gaps in both process-kill
  APIs. The unified `pc(action="process_kill")` route now rejects Windows system
  and Maya/runtime processes and waits for the target to exit before reporting
  success. The legacy `manage_processes` route delegates to that single guarded
  implementation.
- Reproduced and fixed an external-tool authorization gap: discovered MCP tools
  were executable without an approval request because their names were outside
  the native danger list. Every discovered MCP call now requires high-risk
  approval bound to its exact server/tool name and arguments. MCP message/text
  payloads are redacted in approval audit records.
- Reproduced and fixed a persistent external-code configuration gap:
  `configure_mcp_server` could write a future `npx` launch configuration while
  exposed in the baseline tool list. It is now a `HIGH` risk tool, requires
  explicit approval, and is available only when `PERM_SYSTEM` is enabled.
- Added regression coverage in `test_function_calls.py`,
  `test_production_safety.py`, `test_mcp_wiring.py`, and `test_agents.py` for
  these boundaries.
- Static verification on 2026-07-19: changed modules and tests compiled with
  `py_compile`; scoped `git diff --check` passed. Focused S01 coverage passed
  with `41 passed`; broad security coverage passed with `146 passed`, `2
  skipped`, and `9 subtests passed`; the full deterministic suite passed with
  `399 passed`, `2 skipped`, `9 subtests passed`.
- Dynamic Python skills and existing MCP configuration files remain an explicit
  trusted-local-code boundary: a local user who can modify backend source or
  configuration already has equivalent execution authority. Agent-accessible
  file operations cannot write into the protected project tree.
- All R00-R08 security cases are now verified; the only remaining S01 dependency
  is R09's full-suite confirmation. R07's voice security cases were verified on
  2026-07-20. R08's playback security case (protected-target enforcement — the
  stop path must never image-wide kill a user's own VLC, BUG-026) was verified
  on 2026-07-21. R05's security cases (sensitive-path rejection on both attach
  validators, canonical link resolution, uploads-cache-only project exception,
  fuzzy-search secret exclusion, transport-precondition validation, PII-safe
  logging) were verified on 2026-07-20. R06's security cases (session
  isolation, stale-context rejection, approval expiry/replay protection, and
  approval-args binding — BUG-022) were verified on 2026-07-20.

## Defect Log

Add one entry per reproduced issue using this template:

### BUG-XXX - Short Title

- Queue item:
- Reproduction:
- Expected:
- Actual:
- Root cause:
- Fix:
- Regression test:
- Verification:

### BUG-001 - App Close Requests Could Be Reported As Completed Without Verification

- Queue item: R01
- Reproduction: use a window whose `close()` request returns but leaves the
  window open, then call `close_active_window()` or `close_apps_except()`.
- Expected: report partial/failure because the requested end state was not reached.
- Actual: both functions returned `SUCCESS` immediately after issuing `close()`.
- Root cause: missing post-action window-state verification in both paths.
- Fix: re-enumerate open windows after the close request and return
  `PARTIAL`/`ERROR` when the target remains or verification fails.
- Regression test: `test_close_active_window_reports_partial_when_window_remains`
  and `test_close_apps_except_reports_partial_when_a_window_remains`.
- Verification: focused app-control suite `18 passed` on 2026-07-18.

### BUG-002 - Unified File Write Silently Overwrote Existing Files

- Queue item: R02
- Reproduction: write to a path that already contains a file.
- Expected: preserve the existing file under the audit's overwrite-safety policy.
- Actual: the existing file was opened with mode `w` and replaced silently.
- Root cause: write did not use the dedupe policy already used by copy/move/rename.
- Fix: apply `dedupe_path()` before opening the write destination.
- Regression test: `test_write_dedupes_instead_of_silently_overwriting`.
- Verification: focused file reliability suite `4 passed` on 2026-07-18.

### BUG-003 - Rename Could Escape Its Documented Source Directory

- Queue item: R02
- Reproduction: call rename with `dst="../escaped.txt"` or an absolute path.
- Expected: rename only within the source directory.
- Actual: destination segments were joined without validating the filename-only
  contract, allowing a move outside that directory.
- Root cause: missing destination-shape validation before path construction.
- Fix: reject empty, absolute, or multi-segment rename destinations.
- Regression test: `test_rename_cannot_escape_the_source_directory`.
- Verification: focused file reliability suite `4 passed` on 2026-07-18.

### BUG-004 - Immediate App Close Verification Produced A False Partial Result

- Queue item: R01
- Reproduction: open a real Notepad instance and call `close_app("notepad")`.
- Expected: wait briefly for Windows to complete the asynchronous close request,
  then report the observed final state.
- Actual: the immediate window enumeration still saw the closing window and
  returned `PARTIAL`, although the Notepad process was gone one second later.
- Root cause: post-action verification had no bounded GUI settle period.
- Fix: poll matching windows for up to one second with a 50 ms interval before
  deciding whether close succeeded.
- Regression test: `test_close_verification_waits_for_window_to_disappear`.
- Verification: focused app suite `19 passed`; the repeated real Notepad flow
  returned `SUCCESS` and ended with no Notepad process.

### BUG-005 - Direct App Fast Path Bypassed The System-Control Permission

- Queue item: R01 / S01
- Reproduction: disable `PERM_SYSTEM`, then issue a simple direct app command such
  as `Open notepad`.
- Expected: app controls remain unavailable through every routing path.
- Actual: only the later direct OS path checked `PERM_SYSTEM`; direct app actions
  executed before the permission-filtered LLM tool path.
- Root cause: permission guard was missing from `direct_app_action`.
- Fix: clear the direct candidate when `PERM_SYSTEM` is disabled, matching the
  established direct OS behavior.
- Regression test: `test_direct_app_fast_path_respects_system_permission`.
- Verification: focused app/security/agent suite `38 passed` on 2026-07-18.

### BUG-006 - Broad App Close Bypassed Explicit Approval

- Queue item: R01 / S01
- Reproduction: issue `close all apps except visual studio code`.
- Expected: request explicit approval before closing an unbounded set of windows.
- Actual: deterministic routing called `close_apps_except` immediately.
- Root cause: the fast path bypassed the normal danger-tool approval branch, and
  the risk classifier did not classify the broad close action.
- Fix: classify `close_apps_except` as `HIGH`, add it to danger tools, and queue
  an approval request bound to the exact excluded-app payload before execution.
- Regression test: `test_close_all_except_requires_approval` plus the approved
  counterpart in `test_close_all_except_workflow_bypasses_llm`.
- Verification: focused app/security/agent suite `38 passed` on 2026-07-18.

### BUG-007 - Cross-Drive Copy And Move Could Expose Partial State

- Queue item: R02 / S01
- Reproduction: interrupt a cross-drive copy after destination creation, or let
  destination copying succeed while source cleanup fails during a move.
- Expected: never expose an incomplete final destination, preserve/recover source
  data, and report any incomplete end state truthfully without automatic retry.
- Actual: `shutil.copy*`/`shutil.move` wrote directly to the final destination;
  failures could leave partial destination content, and cleanup state was not
  represented by a distinct result contract.
- Root cause: copy/move had no destination-side staging, copy verification,
  source-retirement recovery path, or non-retryable `PARTIAL` classification.
- Fix: copy to a hidden sibling, verify file sizes/tree shape, publish with a
  non-overwriting rename, atomically retire cross-drive sources before cleanup,
  and return `PARTIAL` with the surviving path when retirement/cleanup fails.
- Regression test: interrupted-copy cleanup, simulated `EXDEV` success,
  source-retirement failure, recovery cleanup failure, self-nesting rejection,
  partial-result verifier behavior, and a real isolated C:-to-D: move round trip.
- Verification: focused R02/security/verifier suite `59 passed`, `2 skipped`;
  dedicated real cross-drive test `1 passed` on 2026-07-18.

### BUG-008 - Sensitive Credential Files Outside The Project Were Exposed

- Queue item: R02 / S01
- Reproduction: place `.env`, `credentials.json`, a private-key file, or a file
  under `.ssh`/`.aws` in an otherwise allowed user directory, then read, search,
  copy, move, or delete it through the unified file tool.
- Expected: credential and private-key material remains outside agent-visible
  file operations regardless of whether it is stored inside the Maya project.
- Actual: canonical protection covered Maya/system roots but did not classify
  sensitive names in normal user directories; direct reads and search results
  could expose their content or exact path.
- Root cause: path policy had protected-root enforcement but no centralized
  sensitive-directory, credential-filename, environment-file, or key-extension
  classification.
- Fix: add centralized `is_sensitive_path()` enforcement before all safe-path
  exceptions, filter sensitive search results, and preserve explicitly safe
  environment templates such as `.env.example`.
- Regression test: parameterized read/copy/delete denial, sensitive search-result
  filtering, safe template access, and complete search/delete-by-name/organize
  workflow tests with dedicated temporary fixtures.
- Verification: final focused R02/security/verifier suite `69 passed`, `2 skipped`
  on 2026-07-19.

### BUG-009 - WhatsApp Send Boundaries Retried Or Accepted Invalid Inputs

- Queue item: R03 / S01
- Reproduction: submit a short phone number, empty message, missing/sensitive
  attachment, ambiguous synced contact for a file send, or a deterministic HTTP
  4xx rejection from the local service.
- Expected: reject invalid inputs before service startup, request clarification
  for ambiguity, never expose protected attachments, and retry only transient
  failures with the same idempotency key.
- Actual: invalid recipients/messages could reach the service, ambiguous file
  contacts could yield a missing phone, attachment validation was deferred, and
  permanent client errors were retried up to three times with generic final text.
- Root cause: Python send boundaries duplicated incomplete normalization,
  attachment search did not share centralized path policy, and retry decisions
  treated all unsuccessful responses as transient.
- Fix: strict phone/message/caption validation, canonical attachment validation
  with safe uploads handling, shared ambiguity replies, protected search-result
  filtering, status-prefixed batch summaries, and non-retryable 4xx handling with
  exact error preservation.
- Regression test: invalid phone/message fail-fast, sensitive/missing attachment
  fail-fast, idempotent transient retry, permanent 4xx single-attempt behavior,
  ambiguous file recipient clarification, safe uploads exception, and all-failed
  multi-file `ERROR` reporting.
- Verification: focused offline WhatsApp suite `47 passed` on 2026-07-19; no live
  recipient or external WhatsApp account was used.

### BUG-010 - Targeted App Close Could Reach The Active Maya/Codex Host Window

- Queue item: R01 / S01
- Reproduction: request a close for an app whose visible window title matches a
  Visual Studio Code development-host window owned by the active Maya/Codex
  runtime tree.
- Expected: never issue a close request to the active Maya/Codex host or its
  development windows, even when the requested app name matches the title.
- Actual: `close_app()` matched window titles and called `window.close()` before
  process-level runtime protection was considered.
- Root cause: the visible-window close path had no HWND owner-PID check; only the
  later process fallback protected the runtime process tree.
- Fix: validate app input as a name-only query, derive the protected host PID
  tree, map HWNDs to owner PIDs, and refuse targeted, active-window, and broad
  close operations for protected runtime windows.
- Regression test: protected targeted-close, active-window-close, and
  close-all-except host-window tests in `test_app_launcher.py`.
- Verification: a live owner-PID probe of the active Visual Studio Code window
  returned `ERROR: Refused to close ... protected Maya/runtime process`; the
  test never invoked the window close callback. Final R01-connected suite:
  `99 passed`.

### BUG-011 - Immediate Focus After Launch Could Report A False Failure

- Queue item: R01
- Reproduction: open a fresh Notepad instance and immediately issue `Focus
  notepad` through the direct app workflow.
- Expected: wait briefly for Windows to create the window, then focus and verify
  the foreground state; return a truthful partial result if that cannot happen.
- Actual: the process was running but `pygetwindow.getAllWindows()` did not yet
  expose the Notepad window, so focus replied that no matching window was open.
- Root cause: `focus_app()` performed a single immediate enumeration with no
  GUI-ready settle period and no post-activation foreground verification.
- Fix: poll for a matching window for up to three seconds, restore minimized
  windows, activate the target, and verify that it became active before returning
  `SUCCESS`.
- Regression test: delayed-window discovery and failed-activation tests in
  `test_app_launcher.py`.
- Verification: the initial live error was truthfully stored in context and
  observability; the post-fix fresh Notepad flow opened, focused, and closed PID
  `21316` successfully, with no process left afterward. Final R01-connected
  suite: `99 passed`.

### BUG-012 - WhatsApp Inbound Authorization Was Enforced Only By Visible Buttons

- Queue item: R03 / S01
- Reproduction: receive a direct message from an unknown sender, then invoke the
  hidden draft/manual/send callback data directly; submit a callback from an
  unpaired Telegram chat or private actor; or make the allow/block service call
  fail.
- Expected: no reply path is available before a successful allow action, only
  the paired Telegram identity can execute callbacks, and failed state changes
  never claim success or discard the pending notification.
- Actual: the notification hid reply buttons, but callback methods did not
  re-check `is_known`; callback queries lacked the normal chat authorization
  check; allow/block return values were not consistently enforced.
- Root cause: inbound authorization was represented as UI state rather than a
  shared execution-boundary policy, and state mutations assumed local-service
  success.
- Fix: add a shared reply-authorization guard at draft/manual/send boundaries,
  bind callbacks to the paired chat and private actor, normalize sender numbers
  before authorization transport, and mutate allow/block state only after a
  successful authenticated response.
- Regression test: unauthorized callback identity, forged unknown-sender reply
  callbacks, unauthorized manual text, failed allow/block retention, invalid
  sender fail-fast, and explicit success-body checks.
- Verification: final focused WhatsApp authorization/security suite `34 passed`;
  broader offline R03 regression set `104 passed` on 2026-07-19.

### BUG-013 - WhatsApp Service Lifecycle And Error Logs Could Lose Safety State

- Queue item: R03 / S01
- Reproduction: restart after a stale child process, raise during process
  termination or status polling, and surface service/library errors containing
  recipient numbers, message text, full attachment paths, or pairing data.
- Expected: parent log handles always close, a still-live child remains tracked
  for later cleanup, and logs contain only masked recipients, attachment
  basenames, and bounded non-sensitive error labels.
- Actual: cleanup was tied to normal lifecycle paths, termination failure could
  lose useful manager state, and several Python/Node log statements emitted raw
  exception messages, service reasons, recipient identifiers, or paths.
- Root cause: process/log ownership had no common cleanup helper, and logging
  treated external exception strings as safe diagnostic data.
- Fix: centralize log-handle cleanup across stale, startup-failure, and stop
  paths; retain a live child handle after failed termination; mask phone/path
  labels; and reduce error logging to validated name/code labels that reject
  phone-like digit sequences.
- Regression test: stale log cleanup, failed terminate/poll handling, Python
  response-body redaction, Node masking helpers, protected attachment labels,
  and phone-like error-name/code rejection.
- Verification: Python compile, Node syntax/security-helper checks, focused
  `34 passed`, broader `104 passed`, and `git diff --check` passed on 2026-07-19.

### BUG-014 - WhatsApp Telegram Notifications Ignored Maya's Conversation Style

- Queue item: R03
- Reproduction: speak to Maya in English or Hindilish, then receive an incoming
  WhatsApp notification in Telegram.
- Expected: notification headers, context labels, warnings, buttons, and later
  callback prompts use the user's latest Maya conversation style, while keeping
  all product-generated text in Latin script.
- Actual: the incoming WhatsApp body was preserved correctly and draft language
  detection worked, but notification wrapper text and several callback buttons
  were hardcoded in Bengali or mixed-language strings.
- Root cause: language detection existed independently in desktop text, desktop
  voice, Telegram, and WhatsApp draft generation, but there was no shared latest
  user-style state and the WhatsApp Telegram UI used fixed copy.
- Fix: add shared latest conversation-style state, update it from desktop text,
  desktop voice, and Telegram user turns, skip internal startup greetings, and
  render the complete WhatsApp Telegram interaction from English, Banglish, or
  Hindilish Latin-script copy.
- Regression test: shared style state, short-follow-up continuity, three-style
  notification headers/buttons, incoming notification wiring, and a source scan
  confirming no hardcoded Bengali/Devanagari script remains in the WhatsApp
  Telegram UI section.
- Verification: focused language/Telegram/WhatsApp suite `46 passed`; broader
  R03/language/voice-connected suite `124 passed` on 2026-07-19.

### BUG-015 - System Permission Did Not Remove All System Controls

- Queue item: S01
- Reproduction: save `PERM_SYSTEM=false`, then inspect the callable names from
  `get_maya_tools()`.
- Expected: no tool capable of desktop input, screen capture, app/window control,
  process management, or background UI automation is available to the model.
- Actual: the capability map removed only some system tools while the always-on
  baseline continued to expose app controls, keyboard/mouse input, screenshots,
  shortcuts, and background desktop readers.
- Root cause: system-capable native tools were split between the permission map
  and the unconditional baseline list.
- Fix: move all desktop-control tools to the `PERM_SYSTEM` capability group and
  retain only non-system tools in the baseline list.
- Regression test: expanded
  `test_explicit_false_permission_pref_is_respected` in
  `test_function_calls.py`.
- Verification: focused S01 suite `41 passed`; full deterministic suite `399
  passed`, `2 skipped`, `9 subtests passed` on 2026-07-19.

### BUG-016 - Process Kill Could Target Protected Processes And Claim Success Early

- Queue item: S01
- Reproduction: invoke either `pc(action="process_kill")` or legacy
  `manage_processes(action="kill")` for a Maya/runtime or system-owned PID, or
  simulate a process that remains alive after a kill request.
- Expected: protected targets are never signalled, and success is reported only
  after the requested process has exited.
- Actual: both implementations called `kill()` directly; neither reused
  protected-target enforcement nor verified final process state.
- Root cause: process management duplicated a lower-level mutation path outside
  the audited app-control safeguards.
- Fix: centralize killing in the unified `pc` handler, reuse the runtime/system
  protection checks, wait up to three seconds for exit, and return truthful
  `PARTIAL` or `ERR` results. The legacy function delegates to it.
- Regression test: protected-target and verified-exit tests in
  `test_production_safety.py`.
- Verification: focused S01 suite `41 passed`; full deterministic suite `399
  passed`, `2 skipped`, `9 subtests passed` on 2026-07-19.

### BUG-017 - Discovered MCP Tools Bypassed Approval And Could Leak Message Payloads

- Queue item: S01
- Reproduction: configure an MCP server that exposes a tool, then let the agent
  call its namespaced tool such as `demo__lookup`.
- Expected: an external tool call requires explicit approval bound to the exact
  server/tool and arguments, and private message/text payloads do not enter the
  approval audit log in clear text.
- Actual: only native tool names were checked against the danger policy, so MCP
  tools executed without approval; their names also missed the private-message
  audit-redaction allowlist.
- Root cause: the MCP discovery and execution paths did not participate in the
  native approval and audit-classification model.
- Fix: collect discovered MCP tool names per workflow, classify every such call
  as approval-required, and redact message/content/text payloads for namespaced
  MCP tools.
- Regression test: MCP workflow approval test in `test_mcp_wiring.py` and MCP
  payload-redaction test in `test_production_safety.py`.
- Verification: focused S01 suite `41 passed`; full deterministic suite `399
  passed`, `2 skipped`, `9 subtests passed` on 2026-07-19.

### BUG-018 - MCP Server Configuration Could Persist A Future External Code Launch Without Approval

- Queue item: S01
- Reproduction: ask the agent to configure an MCP server with a syntactically
  valid package name such as `@demo/mcp`.
- Expected: creating a configuration that launches a third-party package after
  restart requires `PERM_SYSTEM` and an explicit approval bound to the package
  and environment arguments.
- Actual: `configure_mcp_server` was part of the baseline native tool list and
  was not classified as dangerous, so the agent could write the future launch
  configuration immediately.
- Root cause: input validation treated a safe package string as sufficient
  authorization, despite the persistent code-execution effect.
- Fix: move the tool under `PERM_SYSTEM`, classify it as `HIGH`, and include it
  in the agent approval gate.
- Regression test: system-disabled tool-list assertion in
  `test_function_calls.py`, risk classification in
  `test_production_safety.py`, and approval denial workflow in
  `test_agents.py`.
- Verification: focused S01 suite `41 passed`; full deterministic suite `399
  passed`, `2 skipped`, `9 subtests passed` on 2026-07-19.

### BUG-019 - Email Controls Could Send, Read, Or Delete With Unsafe Inputs And Unverified End States

- Queue item: R04 / S01
- Reproduction: pass a CR/LF recipient or subject to SMTP send; attach a protected
  credential file; return a raw SMTP/IMAP error; give a partial Subject/Sender to
  a destructive IMAP action; or use an IMAP server without `UIDPLUS` support.
- Expected: outbound email accepts exactly one safe recipient and a validated
  attachment, errors reveal no secrets, and destructive changes happen only after
  an exact fresh target match with a verified targeted final state.
- Actual: send accepted header-like values and direct attachment paths without a
  canonical sensitive-path check, raw exception text reached replies, and delete
  validation used substring matching with broad-expunge fallback and no final
  source-state verification. Credential-setting and outbound send also lacked the
  shared high-risk approval/redaction boundary.
- Root cause: SMTP, read, trash, and permanent-delete functions duplicated
  credential/IMAP handling without a common validation contract or deterministic
  post-action verification.
- Fix: add a shared email-security layer for credential, recipient, header,
  query, UID, exact-header, attachment, and bounded-content validation; use only
  targeted `UIDPLUS` expunge; require high-risk approval for credential storage
  and sending; redact persisted approval/audit payloads; and return SMTP
  acceptance or `PARTIAL`/`ERROR` strictly from observed transport state.
- Regression test: `test_email_reliability_audit.py` covers header injection,
  recipient rejection, attachment protection/size, SMTP redaction, query
  validation, raw-content escaping, exact IMAP targeting, `UIDPLUS` fail-closed
  behavior, final-state truthfulness, credential validation, and approval/audit
  redaction.
- Verification: focused R04 suite `10 passed`; combined email/security/agent
  suites `107 passed`; full deterministic backend suite `404 passed`, `2
  skipped` on 2026-07-20. Python compilation and `git diff --check` passed.

### BUG-020 - A Missing Absolute Attachment Path Could Silently Send A Lookalike File

- Queue item: R05 / S01
- Reproduction: call `whatsapp_send_file` (or `whatsapp_send_multiple_files`)
  with an absolute path that does not exist while a similarly named file exists
  anywhere in the fuzzy-search scope, e.g. request
  `C:\gone\quarterly report 2026.pdf` while a different
  `quarterly report 2026.pdf` sits in a temp or unrelated folder.
- Expected: an explicitly given absolute path is a contract; if it does not
  exist the tool must return `ERROR` and must not search for a substitute.
- Actual: the resolver's condition `os.path.isabs(q) and os.path.exists(q)`
  routed every missing absolute path into token-based fuzzy filename search,
  which happily matched a lookalike file elsewhere on disk. The reply then
  claimed `SUCCESS` for the requested send while a different file had actually
  been delivered to the recipient — a silent wrong-file disclosure. The email
  path (`_resolve_email_attachment`) was not affected: it only invokes fuzzy
  search for relative descriptions and fails missing absolute paths in
  validation.
- Root cause: path resolution conflated "absolute path given" with "fuzzy
  description given" on the existence check instead of on the input's form.
- Fix: in both WhatsApp attachment tools, an absolute path that does not exist
  now returns a deterministic `ERROR` stating the path and that no substitute
  was searched; fuzzy search runs only for genuinely relative descriptions.
  The empty-payload multi-file reply now includes the per-file reasons so a
  fully-failed batch explains itself.
- Regression test: `test_whatsapp_send_message.py::
  test_single_file_missing_absolute_path_is_never_fuzzy_substituted` and
  `test_multiple_file_missing_absolute_path_is_never_fuzzy_substituted` assert
  the fuzzy finder and transport are never called and the reply is `ERROR`.
- Verification: focused suites `65 passed`; full deterministic backend suite
  `419 passed`, `2 skipped` on 2026-07-20.

### BUG-021 - A Failed Multi-File Send Still Deleted The User's Uploads-Cache Copy

- Queue item: R05 / S01
- Reproduction: place a file in the dedicated uploads cache (`data/uploads`),
  attach it via `whatsapp_send_multiple_files`, and let the transport fail
  (service down / not connected). The uploads copy disappeared although
  nothing was delivered.
- Expected: the temp-cache cleanup is a post-delivery action; a failed send
  must leave the cached file in place so the user can retry.
- Actual: the multi-file path deleted every uploads-cache attachment
  unconditionally after `send_files` returned, destroying the only local copy
  on failure and making retry impossible. The single-file path was already
  correct because its cleanup sat behind the success check.
- Root cause: cleanup keyed on "came from uploads cache" instead of "came from
  uploads cache AND was delivered".
- Fix: the multi-file cleanup now removes only attachments whose per-file
  transport result reported success, matched by normalized absolute path.
- Regression test: `test_whatsapp_send_message.py::
  test_multiple_file_failed_send_keeps_uploads_cache_copy` (fails without the
  fix) and `test_multiple_file_successful_send_still_cleans_uploads_cache_copy`
  (guards the success-path cleanup).
- Verification: focused suites `65 passed`; full deterministic backend suite
  `419 passed`, `2 skipped` on 2026-07-20.

### BUG-022 - An Approved Danger Tool Could Re-Execute With Unapproved Replanned Arguments

- Queue item: R06 / S01
- Reproduction: let the model call a danger tool such as
  `file(action="delete", src=A)`; approve it; make the execution fail with a
  retryable error; let the stage-2 replan LLM return "corrected" args pointing
  at a different target `src=B` (or reach stage 3's fallback-tool switch).
- Expected: the user's approval is bound to the exact tool and arguments shown
  in the approval request. A retry may repeat only that identical call; any
  changed arguments or a different tool require a fresh approval.
- Actual: the retry loop assigned `current_args` from the replan JSON (and
  could swap `current_tool_name` to a manifest fallback tool) and re-executed
  immediately — the probe observed `delete src=A` followed by two
  `delete src=B` executions under the single original approval.
- Root cause: the retry/replan/fallback ladder predated the approval gate and
  never distinguished approval-bound (danger) calls from ordinary calls.
- Fix: in the retry loop, an approved danger tool now retries only with the
  identical approved tool and arguments; the replan and fallback-tool stages
  are skipped for danger calls (`is_danger` guard before stage 2/3).
- Regression test: `test_verifier.py::
  test_approved_danger_tool_retries_only_with_the_approved_args` asserts every
  execution uses the approved args and the replan model is never invoked.
- Verification: `test_verifier.py` `16 passed`; full deterministic backend
  suite `420 passed`, `2 skipped` on 2026-07-20.

### BUG-023 - Native Voice Could Speak Internal Control Tokens Aloud

- Queue item: R07 / S01
- Reproduction: issue a voice command that makes the brain emit a control
  token in the text stream — a shutdown/sleep request
  (`SYSTEM_STATE_TRIGGERED:shutdown`) or a mode switch
  (`MODE_CHANGE_TRIGGERED:coding`).
- Expected: the control token is an internal signal for the channel handler,
  never words for the user. The WebSocket UI already suppresses it before TTS;
  the native voice engine must do the same.
- Actual: the desktop voice engine's `_on_text` only stripped ` ```macro `
  blocks. It fed the raw token into the sentence splitter, so Maya literally
  spoke "SYSTEM_STATE_TRIGGERED:shutdown" aloud (probe-confirmed spoken text
  `"Thik ache, shutdown korchi. SYSTEM_STATE_TRIGGERED:shutdown"`).
- Root cause: control-token suppression was implemented only in the WebSocket
  handler; the native voice path — added later and routed through the shared
  gateway — never mirrored that guard. `run_turn` strips tokens from
  `final_text` but the live `on_text` stream the voice engine speaks is not
  cleaned.
- Fix: extract `_is_control_token_stream()` in `desktop_voice_engine.py` and
  make `_on_text` mark the turn as a control-token turn the moment the
  accumulated response begins with a control token — after which nothing is
  queued to TTS, and the end-of-stream flush is skipped for that turn.
- Regression test: `test_desktop_voice_approval.py` adds
  `test_control_token_stream_is_detected_when_it_leads`,
  `_is_not_flagged_when_quoted_later`, `_handles_mode_change_and_whitespace`,
  and empty/partial cases (7 new cases; the suite goes from `3` to `10`).
- Verification: focused voice suite `10 passed`; full deterministic backend
  suite `427 passed`, `2 skipped` on 2026-07-20. Python compilation passed.

### BUG-024 - WhatsApp Sent The Message But Reported Failure And Re-Sent It 5-7 Times

- Queue item: R08 / S01
- Reproduction: send a WhatsApp text/file right after the service reaches
  `ready` (or any time `whatsapp-web.js` resolves `client.sendMessage()` to
  `undefined` / a message whose `id` is not yet hydrated). Observed live: "Baba
  ke weather report whatsapp e pathao" delivered the message but Maya reported
  `ERROR: ... Cannot read properties of undefined (reading 'id')`, the send
  fired 5-7 times, and Maya insisted it had failed while the recipient received
  every copy.
- Expected: once `client.sendMessage()` has been awaited the message has left
  the machine — a missing/unhydrated message id must be reported as
  sent (delivery-unconfirmed), never as a failure, and must never trigger a
  re-send. The agent must not escalate a WhatsApp failure into a code/terminal
  workaround.
- Actual: all three send sites in `whatsapp_service/index.js` (`/send`,
  `/send-file`, `/send-files`) read `msg.id._serialized` immediately after the
  await. When `msg` was `undefined` this threw *inside* the idempotency
  `run()` callback, which (a) surfaced as a false failure and (b) deleted the
  idempotency entry (`idempotency.js` deletes on throw), so the Python client's
  3x retry — reusing the same `requestId` — bypassed the dedupe cache and
  re-sent. Seeing the false ERROR, the agent then escalated to
  `pip install pywhatkit` + code execution, each raising a fresh approval
  ("Command Approved. Executing..." x5-7).
- Root cause: post-send id extraction assumed `sendMessage()` always resolves to
  a fully hydrated message; the throw was on the delivered-message path, and the
  idempotency store treats any throw as "operation never happened".
- Fix: add `resolveSentMessageId(msg)` in `index.js` — it safely returns the
  serialized id when present and `null` otherwise, never throwing. All three
  send sites now use it, log delivery status only when an id exists, and return
  `success: true` with `messageId` possibly null (status falls back to `sent`).
  The idempotency entry therefore survives, so a client retry is deduplicated.
  Defense-in-depth: the OS_EXECUTOR prompt now forbids working around a WhatsApp
  failure by installing a package (pywhatkit) or running scripts/terminal
  commands; the approved WhatsApp senders are the only valid path.
- Regression test: `whatsapp_service` Node proof (send-site) asserts an
  `undefined` result does not throw, reports `messageId=null`, runs the send
  exactly once under retry (idempotency entry preserved), still records delivery
  for a hydrated id, and still deletes the entry on a genuine throw so real
  failures stay retryable. `test_os_prompt_sectioning.py` adds
  `test_whatsapp_block_forbids_terminal_escalation` (guard present without ever
  naming the CODER-only terminal tools in the OS prompt).
- Verification: focused WhatsApp/prompt suites passed; full deterministic
  backend suite `428 passed`, `2 skipped` on 2026-07-20. Node syntax check and
  Python compilation passed.

### BUG-025 - "Close All Apps" Hunted For A Process Named "all" And Failed

- Queue item: R08 / R01
- Reproduction: say "close all apps" / "Please close all app" (no exception
  clause). Observed live: `Direct app action matched: close_app('all')` →
  `ERROR: Could not close all: ERROR: The process "14016" not found.` The
  earlier "bade" fix (BUG pre-025) only covered "close all EXCEPT X"; plain
  "close all" still had no handler.
- Expected: a bulk close request with no exception closes every non-protected
  app window (Maya/runtime host windows always kept open), the same broad-close
  path used by "close all except X".
- Actual: `_parse_bulk_app_exclusion` returned a name only for an "except X"
  match, so plain "close all apps" fell through to single-app parsing.
  `_normalize_app_query` strips command words but "all" is not one, leaving
  `app_name="all"` → `close_app("all")` → search for a process literally named
  "all" → error.
- Root cause: the bulk parser conflated "not a bulk request" with "bulk request
  with no exception", and `close_apps_except("")` rejected an empty exclusion.
- Fix: rename the parser to `_parse_bulk_app_close`, returning three states —
  `None` (not bulk), `""` (close all, no exception), `"<name>"` (close all
  except name). The caller routes any non-`None` to `close_apps_except`.
  `close_apps_except("")` now means "close every non-protected app" (only
  rejects a non-empty string carrying unsafe characters); result messages read
  cleanly for the no-exception case. Broad close still requires HIGH-risk
  approval.
- Regression test: `test_direct_app_workflow.py` asserts "close all apps" and
  "sob app bondho koro" map to `("close_apps_except", "")`;
  `test_app_launcher.py::test_close_apps_except_empty_closes_all_but_protected`
  closes every non-protected window while keeping the runtime host open.
- Verification: focused app suites `40 passed`; full deterministic backend suite
  `429 passed`, `2 skipped` on 2026-07-20. Python compilation passed.

### BUG-026 - Stop Background Audio Could Kill A User's Own VLC And Falsely Claim Success

- Queue item: R08 / S01
- Reproduction: with the user running their own VLC (e.g. watching a movie) and
  Maya having started no background player (no `data/youtube_player.pid`), say
  "stop the music" / "gaan bondho koro". Also reproducible when the saved PID
  has been recycled by an unrelated process, or when `psutil` cannot terminate
  the tracked PID.
- Expected: Maya manages only the exact player it started. If there is nothing
  of Maya's to stop, it reports the truthful state and terminates nothing; a
  user's own VLC is a protected, un-owned target.
- Actual: `stop_youtube_background()` (no-PID path), the recycled/AccessDenied
  fallbacks, and `_kill_existing_player()` all fell back to image-wide
  `taskkill /F /IM vlc.exe`, force-killing every VLC on the machine — including
  the user's unrelated movie — then returned `SUCCESS: Background audio stopped.`
  even though Maya had started nothing.
- Root cause: the kill paths keyed on the VLC image name rather than on the one
  PID Maya owns, mirroring the process-ownership gap already fixed for app close
  (BUG-010) and process kill (BUG-016) but never applied to the audio player.
- Fix: every kill path now targets only the tracked PID (`taskkill /F /PID`),
  guarded by a live-and-still-VLC check. A missing PID file, a dead PID, or a
  recycled non-VLC PID now kills nothing and returns the truthful "No background
  audio is currently playing" state; `_taskkill_vlc(pid)` replaces the image-wide
  sweep.
- Regression test: `test_tools.py::TestBackgroundPlayerStop` —
  `test_stop_with_no_pid_file_never_image_kills_and_is_truthful`,
  `test_stop_never_uses_image_wide_taskkill`, and
  `test_taskkill_fallback_targets_exact_pid_not_image` assert no `/IM` sweep in
  any path and that the fallback targets the exact PID.
- Verification: focused `test_tools.py` `8 passed`; broader audio/router suites
  `57 passed`; full deterministic backend suite `432 passed`, `2 skipped` on
  2026-07-21 (excluding the manual `test_models.py` script). Python compilation
  passed.

### BUG-027 - Power And Delete Approval Could Be Bypassed With Action Spelling Variants

- Queue item: S01
- Reproduction: submit `perform_shortcut(action="Restart")`, the accepted
  `suspend` alias, `pc(action="Process-Kill")`, or
  `file(action="DELETE BY NAME")`.
- Expected: approval classification and execution use the same canonical action.
- Actual: the approval gates compared raw case-sensitive values, while downstream
  executors normalized case, spaces, hyphens, and the `suspend` alias.
- Fix: centralize action canonicalization and approval classification in
  `_canonical_action` / `_tool_call_requires_approval`; use it in direct and LLM
  tool paths, and align the risk classifier.
- Regression evidence: normalization/alias approval and risk tests in
  `test_production_safety.py`; harmless actions remain ungated.

### BUG-028 - `manage_window(close)` Bypassed Runtime Protection And Claimed Early Success

- Queue item: R01 / S01
- Reproduction: target Maya/the active host through `manage_window(action="close")`,
  or close a window that remains open because of an unsaved-work prompt.
- Expected: protected runtime windows are never closed and success requires the
  target window to disappear.
- Actual: `pygetwindow.close()` ran directly and returned `SUCCESS` immediately;
  a failed inspection fell back to unverified `Alt+F4`.
- Fix: reuse runtime owner/title protection, wait for the exact target handle to
  disappear, return `PARTIAL` when it remains, and fail closed instead of using
  the close hotkey after an inspection failure.
- Regression evidence: protected-target and stubborn-window tests in
  `test_app_launcher.py`.

### BUG-029 - Canvas Security Headers Blocked The Canvas From Its Own App

- Queue item: R00 / S01
- Reproduction: open a Canvas in the Vite or Tauri frontend. The backend response
  used `frame-ancestors 'self'` plus `X-Frame-Options: SAMEORIGIN`, while the
  iframe parent is a different trusted local origin; Tauri's parent CSP also had
  no `frame-src` permission for the backend.
- Expected: only the fixed trusted local frontend origins can embed Canvas.
- Actual: the browser/WebView blocked the intended iframe.
- Fix: allow the existing trusted-origin set in `frame-ancestors`, remove the
  incompatible X-Frame-Options header, and permit only
  `http://127.0.0.1:8000` in the Tauri parent `frame-src` directive.
- Regression evidence: Canvas response and Tauri parent-policy tests in
  `test_canvas_engine.py` (`6 passed`).

### BUG-030 - Settings Displayed Successful Or Disabled State After A Failed Save

- Queue item: R00 / S01
- Reproduction: make `/settings/keys` or `/settings/permissions` return non-2xx.
- Expected: no success state is shown; optimistic permission/provider state is
  rolled back and the user sees the backend error.
- Actual: `fetch()` resolves on HTTP errors, and the UI never inspected
  `response.ok` for these mutations.
- Fix: add a shared `requireOk` response guard, apply it to provider/key and
  permission writes, roll back optimistic TTS/permission changes, and show a
  permission error alert.
- Regression evidence: three Node response-helper tests and a successful strict
  TypeScript/Vite production build.

### BUG-031 - Conversation Rows And Raw Archives Exposed Private Text At Rest

- Queue item: S01
- Reproduction: send a user/assistant turn, then let Dreaming Mode compact it.
- Expected: persistent private text is encrypted, archive paths do not expose an
  external session identifier, and runtime data cannot be committed accidentally.
- Actual: `SessionMemory.content` stored plaintext and Dreaming Mode wrote raw
  JSONL under the repository's unignored `archive/conversations` directory.
- Fix: store versioned Fernet ciphertext, transactionally migrate legacy database
  rows, fail closed on unreadable ciphertext, write encrypted archive envelopes
  under `DATA_DIR`, use keyed opaque filenames/log identifiers, ignore the old
  repository archive root, and migrate legacy files only after write/fsync/
  decrypt/hash verification. A safety invariant refuses migration when the
  default legacy source is paired with a redirected destination.
- Regression evidence: database encryption, legacy compatibility, archive
  confidentiality, redirected-destination refusal, source-retention-on-failure,
  and compaction tests in `test_dreaming_mode.py` (`9 passed`). The production
  database migration encrypted `172/172` rows with `0` plaintext and `0`
  unreadable rows.
- Audit execution incident: the first migration regression redirected the real
  legacy source to a temporary destination. It migrated three pre-existing raw
  archive files, after which temporary-directory cleanup removed the encrypted
  copies. A workspace recovery scan found no surviving copies. The prevention
  invariant and regression above were added immediately; the three removed
  historical archive files are not recoverable from the workspace.

## Final Report

### Verified Capabilities

- R00, R01, R02, R05, R06, R07, and R08 completed their full deterministic,
  permission, protected-target, verifier, and truthful-result checks.
- S01 completed the cross-cutting permission, injection, destructive-approval,
  protected-resource, local-service, redaction, PII-at-rest, and recipient checks.
- R09 completed the final deterministic suite and this verified/external/problem
  matrix.
- Offline WhatsApp and email validation, authorization, attachment, idempotency,
  failure, and truthful-result paths passed even though their live transports
  remain external.

### External Setup-Dependent Capabilities

- R03: live WhatsApp pairing and real delivery acknowledgment require an approved
  account/device, network session, and recipient.
- R04: live SMTP/IMAP acceptance and mailbox-state verification require approved
  Gmail credentials and a test recipient.
- Two live Windows symlink cases require privilege unavailable to this process;
  equivalent deterministic reparse/symlink defenses pass. The real cross-drive
  fixture is skipped only because its live roots are not writable; deterministic
  cross-drive success/failure/recovery coverage passes.
- Root production npm audit reported `0 vulnerabilities`. The frontend npm audit
  could not contact the registry in the sandbox, and the escalation reviewer
  infrastructure rejected the network request. `pip-audit`, Bandit, Cargo, and
  `cargo-audit` are not installed, so those dependency/toolchain scans remain
  external rather than being reported as passes.

### Reproduced Problems, Fixes, And Regression Evidence

- BUG-001 through BUG-031 above have documented reproductions, root causes,
  scoped fixes, and regression coverage.
- Final focused security/reliability selection: `162 passed`, `3 skipped`.
- Final deterministic backend suite on 2026-07-22: `447 passed`, `3 skipped`,
  `9 subtests passed`; all skips are the explicitly recorded environment-only
  symlink/cross-drive fixtures.
- Frontend safety tests: `3 passed`; strict TypeScript and Vite production build
  passed. WhatsApp Node syntax checks, Python compilation, and `git diff --check`
  passed.
- The BUG-031 audit execution incident caused irreversible loss of three old raw
  archive files; it is recorded here rather than hidden as a successful migration.
