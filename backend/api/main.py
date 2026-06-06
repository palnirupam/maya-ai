from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import logging

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

from backend.database.connection import engine, Base
from backend.database import models # To ensure tables are registered

# Create database tables BEFORE importing routes that instantiate DB singletons
Base.metadata.create_all(bind=engine)

from .websocket.handlers import router as websocket_router
from .routes.settings import router as settings_router

app = FastAPI(title="Maya AI Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(websocket_router)
app.include_router(settings_router)

# ── Voice Engine globals ──────────────────────────────────────────────
_voice_listener = None
_voice_listener_task = None
_active_listener_instance = None  # Reference to current DesktopMicrophoneListener


def get_active_listener():
    """Returns the current DesktopMicrophoneListener instance (or None)."""
    return _active_listener_instance

@app.on_event("startup")
async def startup_event():
    global _voice_listener, _voice_listener_task

    # ── Step 1: Voice Engine (DB + Config already init'd at module level above) ──
    # Startup order: DB → Config → Voice Engine → Telegram → API Ready
    try:
        from backend.voice.voice_state_machine import voice_state_machine, VoiceState
        from backend.voice.input.desktop_listener import start_listener_with_recovery
        from backend.voice.output.desktop_player import desktop_player
        from backend.voice.desktop_voice_engine import desktop_voice_engine

        desktop_player._sm = voice_state_machine  # inject state machine

        # Wrap start_listener_with_recovery to capture the listener instance
        async def _start_listener_and_track():
            global _active_listener_instance
            RETRY_DELAY = 5
            from backend.voice.input.desktop_listener import DesktopMicrophoneListener
            while True:
                listener = DesktopMicrophoneListener(voice_state_machine, barge_in=False)
                _active_listener_instance = listener
                try:
                    await listener.start()
                    while listener._running:
                        await asyncio.sleep(1)
                except Exception as e:
                    logging.error(f"[DesktopListener] Listener crashed: {e}. Retrying in {RETRY_DELAY}s...")
                finally:
                    await listener.stop()
                    if _active_listener_instance is listener:
                        _active_listener_instance = None
                await asyncio.sleep(RETRY_DELAY)

        # Start the mic listener (VAD loop)
        _voice_listener_task = asyncio.create_task(
            _start_listener_and_track()
        )

        # Start the pipeline: queue → STT → Brain → TTS → Speaker
        asyncio.create_task(
            desktop_voice_engine.start(voice_state_machine, None)
        )

        # Set state machine to LISTENING so it starts accepting speech
        await voice_state_machine.transition(VoiceState.LISTENING)

        logging.info("[Startup] Native Desktop Voice Engine ✨ FULLY CONNECTED ✨")
    except Exception as e:
        logging.error(
            f"[Startup] Voice Engine failed to init ({e}). "
            f"Falling back to Telegram-only mode."
        )

    # ── Step 2: Telegram Bot ────────────────────────────────────────────────────
    try:
        from backend.api.telegram_bot import telegram_bot_manager
        telegram_bot_manager.start()
    except Exception as e:
        logging.error(f"Error starting Telegram Bot: {e}")
    try:
        from backend.tools.desktop.advanced.whatsapp_manager import whatsapp_manager
        whatsapp_manager.start()
    except Exception as e:
        logging.error(f"Error starting WhatsApp service: {e}")
    try:
        from backend.system.scheduler import maya_scheduler
        asyncio.create_task(maya_scheduler.start())
    except Exception as e:
        logging.error(f"Error starting Scheduler: {e}")
    try:
        from backend.skills.skill_watcher import start_skill_watcher
        start_skill_watcher()
    except Exception as e:
        logging.error(f"Error starting Skill Watcher: {e}")
    try:
        from backend.skills.md_loader import start_md_skill_loader
        start_md_skill_loader()
    except Exception as e:
        logging.error(f"Error starting MD Skill Loader: {e}")
    try:
        from backend.tools.mcp_service import mcp_service
        asyncio.create_task(mcp_service.start())
    except Exception as e:
        logging.error(f"Error starting MCP Service: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    global _voice_listener_task

    # ── Voice Engine: cancel LLM, flush audio, clean up ────────────────────────
    try:
        from backend.voice.voice_state_machine import voice_state_machine
        await voice_state_machine.cancel_llm()
        # Bounded LLM teardown — never hangs forever
        try:
            await asyncio.wait_for(asyncio.sleep(0), timeout=5.0)  # yield + wait
        except asyncio.TimeoutError:
            logging.warning("[Shutdown] LLM teardown timed out after 5s — proceeding.")

        from backend.voice.output.desktop_player import desktop_player
        await desktop_player.drain_and_stop(timeout=2.0)

        from backend.voice.input.desktop_listener import _release_pid_file
        _release_pid_file()  # ensure PID file cleaned even on crash

        if _voice_listener_task:
            _voice_listener_task.cancel()
    except Exception as e:
        logging.error(f"[Shutdown] Voice Engine shutdown error: {e}")

    try:
        from backend.api.telegram_bot import telegram_bot_manager
        await telegram_bot_manager.stop()
    except Exception as e:
        logging.error(f"Error stopping Telegram Bot: {e}")
    try:
        from backend.tools.desktop.advanced.whatsapp_manager import whatsapp_manager
        whatsapp_manager.stop()
    except Exception as e:
        logging.error(f"Error stopping WhatsApp service: {e}")
    try:
        from backend.system.scheduler import maya_scheduler
        asyncio.create_task(maya_scheduler.stop())
    except Exception as e:
        logging.error(f"Error stopping Scheduler: {e}")
    try:
        from backend.skills.skill_watcher import stop_skill_watcher
        stop_skill_watcher()
    except Exception as e:
        logging.error(f"Error stopping Skill Watcher: {e}")
    try:
        from backend.skills.md_loader import stop_md_skill_loader
        stop_md_skill_loader()
    except Exception as e:
        logging.error(f"Error stopping MD Skill Loader: {e}")
    try:
        from backend.tools.mcp_service import mcp_service
        await mcp_service.shutdown()
    except Exception as e:
        logging.error(f"Error stopping MCP Service: {e}")

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Maya AI Backend is running."}

@app.get("/skills")
def list_skills():
    """Debug endpoint — shows all loaded SKILL.md skills."""
    try:
        from backend.skills.md_loader import get_loaded_skills, MD_SKILLS_REGISTRY
        skills = get_loaded_skills()
        return {
            "status": "ok",
            "count": len(skills),
            "skills": skills,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/voice/stats")
def voice_stats():
    """Debug endpoint — voice engine latency ring buffer (last 1000 requests)."""
    try:
        from backend.voice.voice_state_machine import voice_state_machine
        return {"status": "ok", **voice_state_machine.get_stats()}
    except Exception as e:
        return {"status": "error", "message": str(e)}
