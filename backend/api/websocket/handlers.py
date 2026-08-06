from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from .manager import manager
from ...voice.pipeline.audio_pipeline import AudioPipeline
from ...voice.input.transcriber import transcriber
from ...brain.orchestrator import orchestrator
from ...brain.language_style import (
    BANGLISH,
    detect_conversation_style,
    set_latest_conversation_style,
    tts_language_for_style,
)
from ...voice.output.tts_router import tts_router
from ...voice.emotions.formatter import formatter as emotion_formatter
from ...system.event_bus import system_event_bus
import logging
import base64
import numpy as np
import uuid
import re
from ..security import ClientMessageError, parse_client_event, websocket_boundary_error

logger = logging.getLogger(__name__)
router = APIRouter()

import asyncio

active_tasks = {}

def cancel_active_tasks(session_id: str):
    cancelled = []
    if session_id in active_tasks:
        for t in active_tasks[session_id]:
            if not t.done():
                t.cancel()
                cancelled.append(t)
                logger.info(f"Cancelled active task for session {session_id}")
        active_tasks[session_id] = []
    return cancelled

# Forward internal event bus events to frontend WebSockets
async def _forward_mode_change(data):
    await manager.broadcast_event("mode_changed", data)

system_event_bus.subscribe("MODE_CHANGED", _forward_mode_change)

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    rejection = websocket_boundary_error(
        websocket.client.host if websocket.client else None,
        websocket.headers.get("origin"),
    )
    if rejection:
        logger.warning("Rejected WebSocket handshake: %s", rejection)
        await websocket.close(code=1008, reason=rejection)
        return

    await manager.connect(websocket)
    session_id = str(uuid.uuid4())

    def run_generation_task(text_val: str, start_time: float = None):
        cancel_active_tasks(session_id)
        gen_task = asyncio.create_task(process_text_input(text_val, t_speech_end=start_time))
        if session_id not in active_tasks:
            active_tasks[session_id] = []
        active_tasks[session_id].append(gen_task)

    async def process_text_input(text: str, t_speech_end: float = None):
        import time
        if t_speech_end is None:
            t_speech_end = time.time()
            
        t_llm_start = time.time()
        logger.info("Streaming LLM response (input_chars=%d)", len(text))
        
        # Lock one conversational style for the complete voice turn. This keeps
        # short follow-ups on the prior style and lets Latin Banglish/Hindilish
        # use the correct Indian TTS voice without changing the response script.
        is_startup_greeting = text.startswith("SYSTEM_EVENT_STARTUP_GREETING")
        turn_style = (
            BANGLISH
            if is_startup_greeting
            else detect_conversation_style(
                text, orchestrator.sessions.get(session_id, [])
            )
        )
        if not is_startup_greeting:
            set_latest_conversation_style(turn_style)
        turn_language = tts_language_for_style(turn_style)
        
        # Vision Trigger Check (Phase 1 Intent Classifier)
        image_bytes = None
        vision_keywords = ["dekho", "look", "screen", "read", "error", "eta ki", "inspect", "ki lekha", "dekhcho"]
        if any(keyword in text.lower() for keyword in vision_keywords):
            from ...vision.capture.screen_capture import screen_capture
            logger.info("Vision Trigger matched! Capturing active window...")
            capture_result = screen_capture.capture_as_base64()
            
            if capture_result == "ERROR_SENSITIVE_APP":
                logger.warning("Sensitive app detected. Injecting safety notice into LLM prompt.")
                text += "\n[SYSTEM NOTICE: The user asked you to look at the screen, but you are BLOCKED by the security module because a sensitive app (e.g. password manager/bank) is open. Apologize and say you cannot view sensitive screens for their privacy.]"
            else:
                image_bytes = capture_result
        
        # We will stream the LLM response, find sentence boundaries, and TTS them immediately!
        sentence_buffer = ""
        full_response = ""
        is_first_sentence = True
        t_tts_start = 0

        # We need an asyncio Queue to process TTS sequentially to preserve order
        import asyncio
        sentence_queue = asyncio.Queue()

        async def tts_worker():
            while True:
                item = await sentence_queue.get()
                if item is None:
                    sentence_queue.task_done()
                    break
                    
                batch_text, batch_emotion, idx = item
                try:
                    complete_audio = b""
                    async for chunk in tts_router.stream_audio(
                        batch_text,
                        language=turn_language,
                        emotion=batch_emotion,
                    ):
                        complete_audio += chunk

                    if complete_audio:
                        b64_chunk = base64.b64encode(complete_audio).decode("utf-8")
                        await manager.send_personal_event("audio_response", {"audio": b64_chunk, "emotion": batch_emotion}, websocket)
                        if idx == 0:
                            logger.info(f"First batch TTS arrived in {time.time() - t_tts_start:.2f}s")
                except Exception as e:
                    logger.error(f"TTS Stream error for batch: {e}")
                finally:
                    sentence_queue.task_done()

        worker_task = asyncio.create_task(tts_worker())
        if session_id in active_tasks:
            active_tasks[session_id].append(worker_task)
        await manager.send_personal_event("status_update", {"appState": "speaking"}, websocket)

        batch_sentences = []
        batch_text_accum = ""
        batch_idx = 0
        is_system_command = False
        
        async def _on_event(chunk):
            if chunk.get("type") == "tool_call_request":
                await manager.send_personal_event("tool_approval_request", chunk["data"], websocket)
            elif chunk.get("type") == "agent_status":
                await manager.send_personal_event("agent_status", chunk["data"], websocket)

        async def _on_text(visible):
            nonlocal sentence_buffer, full_response, is_first_sentence, is_system_command
            nonlocal batch_sentences, batch_text_accum, batch_idx, t_tts_start
            sentence_buffer += visible
            full_response += visible

            if is_first_sentence and (full_response.startswith("SYSTEM_STATE") or full_response.startswith("MODE_CHANGE")):
                is_system_command = True
                return
                
            if is_system_command:
                return

            match = re.search(r'((?<!\d)[.!?।\u0964]+)', sentence_buffer)
            if not match and len(sentence_buffer) > 250:
                match = re.search(r'((?<!\d)[,;]+)', sentence_buffer)
                
            if match:
                boundary_idx = match.end()
                sentence = sentence_buffer[:boundary_idx].strip()
                sentence_buffer = sentence_buffer[boundary_idx:]
                
                if sentence:
                    sentence = re.sub(r'```macro.*?(?:```|$)', '', sentence, flags=re.DOTALL).strip()
                    if "MODE_CHANGE_TRIGGERED:" in sentence:
                        sentence = sentence.split("MODE_CHANGE_TRIGGERED:")[0].strip()
                        
                    if sentence:
                        if is_first_sentence:
                            t_tts_start = time.time()
                            logger.info(
                                "First sentence generated in %.2fs (chars=%d)",
                                t_tts_start - t_llm_start,
                                len(sentence),
                            )
                            is_first_sentence = False
                        
                        batch_sentences.append(sentence)
                        batch_text_accum += sentence + " "

                        # Reduce batching size from 3 to 1 sentence (or >100 characters) for low-latency streaming
                        if len(batch_sentences) >= 1 or len(batch_text_accum) > 100:
                            combined = batch_text_accum.strip()
                            batch_emotion = emotion_formatter.extract_emotion(combined) or "neutral"
                            sentence_queue.put_nowait((combined, batch_emotion, batch_idx))
                            batch_idx += 1
                            batch_sentences = []
                            batch_text_accum = ""

        # Route the turn through the shared channel gateway: it CoT-strips the
        # text and forwards tool/agent events. on_text does sentence splitting
        # for low-latency TTS. timeout=None keeps the real-time stream unbounded;
        # the gateway flushes any held-back tail into on_text at stream end.
        from ...brain.gateway import run_turn
        await run_turn(
            session_id, text, image_base64=image_bytes,
            on_text=_on_text, on_event=_on_event, timeout=None,
        )

        # Process any remaining text in the buffer
        if not is_system_command and batch_text_accum.strip():
            combined = batch_text_accum.strip()
            combined = re.sub(r'```macro.*?(?:```|$)', '', combined, flags=re.DOTALL).strip()
            if combined:
                if is_first_sentence:
                    t_tts_start = time.time()
                    logger.info(
                        "First sentence generated in %.2fs (chars=%d)",
                        t_tts_start - t_llm_start,
                        len(combined),
                    )
                batch_emotion = emotion_formatter.extract_emotion(combined) or "neutral"
                sentence_queue.put_nowait((combined, batch_emotion, batch_idx))
                batch_idx += 1

        if not is_system_command and sentence_buffer.strip():
            remaining = sentence_buffer.strip()
            remaining = re.sub(r'```macro.*?(?:```|$)', '', remaining, flags=re.DOTALL).strip()
            if remaining:
                batch_emotion = emotion_formatter.extract_emotion(remaining) or "neutral"
                sentence_queue.put_nowait((remaining, batch_emotion, batch_idx))
                batch_idx += 1

        # Handle system commands AFTER the stream finishes gathering
        if is_system_command or "ACTION_TRIGGERED:" in full_response or "```macro" in full_response:
            # Tell worker to stop immediately if it's a shutdown/sleep
            if is_system_command:
                sentence_queue.put_nowait(None)


            # Handle Macro Sequences — gated behind explicit user approval
            # Security: macros execute pyautogui directly on the host OS, so they
            # must go through the same approval pipeline as all other DANGER_TOOLS.
            if "```macro" in full_response:
                try:
                    macro_code = full_response.split("```macro")[1].split("```")[0].strip()
                    import pyautogui
                    import time
                    from ...brain.reasoning.tool_planner import tool_planner

                    # Queue the macro for user approval before running anything
                    req = tool_planner.queue_tool(
                        "execute_macro",
                        {"macro_preview": macro_code[:800]},
                        risk_level="danger",
                    )
                    # Send approval popup to the frontend
                    await manager.send_personal_event("tool_approval_request", req, websocket)
                    logger.info(f"[Macro] Approval requested (id={req['request_id']}). Waiting for user...")

                    try:
                        approved = await asyncio.wait_for(
                            tool_planner.wait_for_approval(req["request_id"]),
                            timeout=300.0,
                        )
                    except asyncio.TimeoutError:
                        approved = False
                        logger.warning("[Macro] Approval timed out (5 min). Auto-denying.")

                    if not approved:
                        logger.warning("[Macro] User denied macro execution — skipping.")
                        await manager.send_personal_event(
                            "assistant_message",
                            {"text": "Macro execution was denied."},
                            websocket,
                        )
                    else:
                        logger.info("[Macro] User approved execution (chars=%d).", len(macro_code))
                        for line in macro_code.split('\n'):
                            line = line.strip()
                            if not line:
                                continue
                            parts = line.split(" ", 1)
                            cmd = parts[0].lower()
                            arg = parts[1] if len(parts) > 1 else ""

                            if cmd == "press":
                                keys = [k.strip() for k in arg.split('+')]
                                if len(keys) > 1:
                                    pyautogui.hotkey(*keys)
                                else:
                                    pyautogui.press(keys[0])
                            elif cmd == "type":
                                pyautogui.write(arg, interval=0.02)
                            elif cmd == "wait":
                                time.sleep(float(arg))
                            elif cmd == "click":
                                pyautogui.click()
                            elif cmd == "click_text":
                                target_text = arg.strip('"').strip("'")
                                from ...vision.capture.screen_capture import screen_capture
                                img, monitor = screen_capture.capture_as_pil()
                                if img and monitor:
                                    from ...vision.ocr.ocr_engine import ocr_engine
                                    processed_img = ocr_engine.preprocess_image(img)
                                    coords = ocr_engine.find_text_coordinates(processed_img, target_text, fuzzy_threshold=0.7)
                                    if coords:
                                        x = monitor["left"] + coords[0]
                                        y = monitor["top"] + coords[1]
                                        logger.info(f"Hovering over '{target_text}' at ({x}, {y}) before clicking...")
                                        pyautogui.moveTo(x, y, duration=0.3)
                                        time.sleep(0.5)
                                        pyautogui.click()
                                    else:
                                        logger.warning(f"OCR failed to find '{target_text}'. Aborting click.")
                                else:
                                    logger.warning("Could not capture screen for OCR (possibly sensitive app).")

                    await manager.send_personal_event("status_update", {"appState": "idle"}, websocket)

                    # Let worker_task finish the conversational parts
                    sentence_queue.put_nowait(None)
                    await worker_task
                    return
                except Exception as e:
                    logger.error(f"Macro execution failed: {e}")
            
            if "SYSTEM_STATE_TRIGGERED:shutdown" in full_response:
                from ...brain.reasoning.tool_planner import tool_planner
                tool_planner.queue_tool("manage_system_state", {"action": "shutdown"}, risk_level="warning")
                from ...system.state_manager import state_manager
                txt = "তুমি কি চাও আমি অ্যাপ্লিকেশনটি বন্ধ করে দিই?" if state_manager.state.active_mode == "friendly" else "Do you want me to close the application?"
                await manager.send_personal_event("assistant_message", {"text": txt}, websocket)
                sentence_queue.put_nowait((txt, "happy", 0))
                await manager.send_personal_event("status_update", {"appState": "idle"}, websocket)
                return

            if "SYSTEM_STATE_TRIGGERED:sleep" in full_response:
                from ...system.shutdown_manager import shutdown_manager
                from ...system.state_manager import state_manager
                txt = "আমি ঘুমাতে যাচ্ছি। প্রয়োজন হলে ডেকে নিও।" if state_manager.state.active_mode in ("friendly") else "Going to sleep. Wake me if you need me."
                await manager.send_personal_event("assistant_message", {"text": txt}, websocket)
                sentence_queue.put_nowait((txt, "romantic", 0))
                await shutdown_manager.trigger_sleep()
                return

            if "MODE_CHANGE_TRIGGERED:" in full_response:
                mode_req = full_response.split("MODE_CHANGE_TRIGGERED:")[1].strip().split()[0]
                from ...system.state_manager import state_manager
                success = await state_manager.change_mode(mode_req)
                if success:
                    logger.info(f"Mode changed to {mode_req}. Re-prompting LLM for acknowledgment.")
                    response_text = await orchestrator.process_user_input(
                        session_id, "Mode changed successfully. Please acknowledge this briefly using your new tone."
                    )
                    logger.info("Maya acknowledgment generated (chars=%d).", len(response_text))
                    # Need to speak the acknowledgment
                    await manager.send_personal_event("assistant_message", {"text": response_text}, websocket)
                    sentences = [s.strip() for s in re.split(r'(?<=[.!?।\u0964])\s+', response_text) if s.strip()]
                    if not sentences:
                        sentences = [response_text]
                    combined = " ".join(sentences)
                    ack_emotion = emotion_formatter.extract_emotion(combined) or "neutral"
                    sentence_queue.put_nowait((combined, ack_emotion, 0))
                    
                    sentence_queue.put_nowait(None)
                    await worker_task
                    await manager.send_personal_event("status_update", {"appState": "idle"}, websocket)
                    return

        # Send the final full text to the frontend history
        await manager.send_personal_event("assistant_message", {"text": full_response}, websocket)

        # Wait for all TTS audio to finish streaming
        if not is_system_command:
            sentence_queue.put_nowait(None)
            await worker_task

        t_total = time.time()
        logger.info(f"Total time from speech end to last audio chunk: {t_total - t_speech_end:.2f}s")
        await manager.send_personal_event("status_update", {"appState": "idle"}, websocket)
        await manager.send_personal_event("session_ready", {}, websocket)

        # Cleanup tasks from active list
        if session_id in active_tasks:
            current_task = asyncio.current_task()
            active_tasks[session_id] = [t for t in active_tasks[session_id] if t != current_task and t != worker_task]

    # Callback triggered by AudioPipeline when VAD detects end of speech
    async def on_speech_end(audio_data: np.ndarray):
        import time
        t0 = time.time()
        await manager.send_personal_event("status_update", {"appState": "thinking"}, websocket)
        logger.info("Transcribing audio...")

        text = await transcriber.transcribe(audio_data)
        t_trans = time.time()
        logger.info("Transcribed in %.2fs (chars=%d).", t_trans - t0, len(text))

        if not text:
            await manager.send_personal_event("status_update", {"appState": "idle"}, websocket)
            return

        await manager.send_personal_event("user_message", {"text": text}, websocket)
        run_generation_task(text, start_time=t0)

    # Instantiate the pipeline for this client
    pipeline = AudioPipeline(session_id=session_id, on_speech_end=on_speech_end)

    await manager.send_personal_event("status_update", {"appState": "idle"}, websocket)

    # Connecting/reconnecting is a transport event, not a user turn. An
    # automatic spoken greeting here makes Maya talk without being addressed
    # and can feed back into an open microphone. Wait for explicit input.

    try:
        while True:
            data = await websocket.receive_text()
            try:
                event_type, payload = parse_client_event(data)
            except ClientMessageError as exc:
                logger.warning("Rejected WebSocket client message: %s", exc)
                await websocket.close(code=1008, reason=str(exc))
                break

            if event_type == "audio_chunk":
                # Placeholder: real VAD pipeline (real-time streaming)
                dummy_pcm = np.zeros(16000 // 4, dtype=np.float32)
                await pipeline.process_chunk(dummy_pcm)

            elif event_type == "audio_end":
                logger.info("Received bounded audio_end event from frontend.")
                audio_b64 = payload.get("audio", "")
                if audio_b64:
                    import tempfile, os
                    audio_bytes = base64.b64decode(audio_b64, validate=True)
                    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
                        f.write(audio_bytes)
                        temp_path = f.name

                    try:
                        await on_speech_end(temp_path)
                    finally:
                        try:
                            os.remove(temp_path)
                        except Exception:
                            pass

            elif event_type == "text_message":
                text = payload.get("text", "")
                if text:
                    await manager.send_personal_event("status_update", {"appState": "thinking"}, websocket)
                    await manager.send_personal_event("user_message", {"text": text}, websocket)
                    run_generation_task(text)

            elif event_type == "user_interrupted":
                logger.info(f"User interrupted session {session_id}. Cancelling active tasks.")
                cancel_active_tasks(session_id)
                await manager.send_personal_event("status_update", {"appState": "idle"}, websocket)

            elif event_type == "tool_approval_response":
                request_id = payload["request_id"]
                approved = payload["approved"]
                from ...brain.reasoning.tool_planner import tool_planner
                result = tool_planner.resolve_tool(request_id, approved)
                logger.info("Resolved approval request %s with status %s.", request_id, result.get("status"))

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected.")
    except Exception:
        logger.exception("WebSocket session failed.")
    finally:
        cancelled_tasks = cancel_active_tasks(session_id)
        if cancelled_tasks:
            await asyncio.gather(*cancelled_tasks, return_exceptions=True)
        active_tasks.pop(session_id, None)
        orchestrator.release_session(session_id)
        manager.disconnect(websocket)
