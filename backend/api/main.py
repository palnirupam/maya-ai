from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
import asyncio
import logging
import os

# Load environment variables from .env as EARLY as possible, before any module
# (gemini_adapter, elevenlabs, transcriber, ...) reads os.getenv at import time.
# Look for .env at the project root regardless of the CWD uvicorn was started in.
from pathlib import Path
from dotenv import load_dotenv
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=_ENV_PATH, override=False)

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
if _ENV_PATH.exists():
    logging.getLogger(__name__).info(f"[Startup] Loaded environment from {_ENV_PATH}")
else:
    logging.getLogger(__name__).warning(
        f"[Startup] No .env file at {_ENV_PATH} — relying on DB / OS environment for keys."
    )

from backend.database.connection import engine, Base
from backend.database import models # To ensure tables are registered

# Create database tables BEFORE importing routes that instantiate DB singletons
Base.metadata.create_all(bind=engine)

# One-time compatibility migration: older SessionMemory rows were plaintext.
# The migration is transactional and leaves already-versioned ciphertext intact.
try:
    from backend.brain.memory.session_security import migrate_legacy_session_rows

    _migrated_session_rows = migrate_legacy_session_rows()
    if _migrated_session_rows:
        logging.getLogger(__name__).info(
            "[Startup] Encrypted %s legacy conversation rows.",
            _migrated_session_rows,
        )
except Exception as exc:
    logging.getLogger(__name__).error(
        "[Startup] Legacy conversation encryption migration failed: %s",
        exc,
    )

from .websocket.handlers import router as websocket_router
from .routes.settings import router as settings_router
from .security import TRUSTED_ORIGINS, http_boundary_error

_DEBUG_ROUTES_ENABLED = os.getenv("MAYA_ENABLE_DEBUG_ROUTES", "").strip().lower() in {
    "1",
    "true",
    "yes",
}

app = FastAPI(
    title="Maya AI Backend",
    version="1.0.0",
    docs_url="/docs" if _DEBUG_ROUTES_ENABLED else None,
    redoc_url="/redoc" if _DEBUG_ROUTES_ENABLED else None,
    openapi_url="/openapi.json" if _DEBUG_ROUTES_ENABLED else None,
)

# ── CORS: only allow Tauri app and local dev servers ─────────────────────────
# Security: wildcard allow_origins=["*"] with allow_credentials=True allows any
# third-party website to make authenticated requests to this backend — CVE-class.
_CORS_ORIGINS = sorted(TRUSTED_ORIGINS)
_CANVAS_FRAME_ANCESTORS = " ".join(("'self'", *sorted(TRUSTED_ORIGINS)))

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.middleware("http")
async def enforce_local_boundary(request: Request, call_next):
    rejection = http_boundary_error(
        request.client.host if request.client else None,
        request.headers.get("origin"),
    )
    if rejection:
        return JSONResponse(status_code=403, content={"detail": rejection})

    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.url.path.startswith("/settings"):
        response.headers["Cache-Control"] = "no-store"
    return response

# Include routers
app.include_router(websocket_router)
app.include_router(settings_router)

# ── Voice Engine globals ──────────────────────────────────────────────
_voice_listener = None
_voice_listener_task = None
_active_listener_instance = None  # Reference to current DesktopMicrophoneListener
_canvas_cleanup_task = None



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

    # ── Step 3: Canvas Auto-Cleanup ─────────────────────────────────────────────
    global _canvas_cleanup_task
    try:
        from backend.system.canvas import clean_inactive_sessions_loop
        _canvas_cleanup_task = asyncio.create_task(clean_inactive_sessions_loop())
        logging.info("[Startup] Canvas auto-cleanup loop started.")
    except Exception as e:
        logging.error(f"Error starting Canvas cleanup loop: {e}")

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

    global _canvas_cleanup_task
    if _canvas_cleanup_task:
        _canvas_cleanup_task.cancel()
        logging.info("[Shutdown] Canvas auto-cleanup loop stopped.")

@app.get("/canvas/{session_id}/{filename:path}")
def get_canvas_file(session_id: str, filename: str):
    """
    Serves static files generated for a specific Canvas session.
    Applies strict CSP headers to isolate the sandbox iframe.
    """
    try:
        from backend.system.canvas import validate_canvas_path
        abs_path = validate_canvas_path(session_id, filename)
        if not os.path.exists(abs_path) or not os.path.isdir(os.path.dirname(abs_path)):
            return JSONResponse(status_code=404, content={"detail": "Canvas file not found"})
        if os.path.isdir(abs_path):
            abs_path = os.path.join(abs_path, "index.html")
            if not os.path.exists(abs_path):
                return JSONResponse(status_code=404, content={"detail": "Canvas file not found"})

        response = FileResponse(abs_path)
        csp_header = (
            "default-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "connect-src 'none'; "
            f"frame-ancestors {_CANVAS_FRAME_ANCESTORS};"
        )
        response.headers["Content-Security-Policy"] = csp_header
        response.headers["X-Content-Type-Options"] = "nosniff"
        # X-Frame-Options cannot express the fixed Tauri/Vite allowlist above;
        # SAMEORIGIN would block the app's intended cross-origin iframe.
        if "X-Frame-Options" in response.headers:
            del response.headers["X-Frame-Options"]
        return response
    except ValueError as e:
        return JSONResponse(status_code=400, content={"detail": str(e)})
    except Exception as e:
        logging.error(f"[Canvas] File serving error: {e}")
        return JSONResponse(status_code=500, content={"detail": "Internal server error serving canvas file"})

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Maya AI Backend is running."}

@app.get("/canvas/latest")
def canvas_latest():
    """Returns the most recently updated canvas session info for frontend polling."""
    from backend.system.canvas import CANVAS_DIR
    try:
        if not os.path.exists(CANVAS_DIR):
            return {"session_id": None, "updated_at": 0}
        best = None
        best_mtime = 0
        for name in os.listdir(CANVAS_DIR):
            path = os.path.join(CANVAS_DIR, name)
            index = os.path.join(path, "index.html")
            if os.path.isdir(path) and os.path.exists(index):
                mtime = os.path.getmtime(index)
                if mtime > best_mtime:
                    best_mtime = mtime
                    best = name
        return {"session_id": best, "updated_at": best_mtime}
    except Exception as e:
        return {"session_id": None, "updated_at": 0, "error": str(e)}

async def canvas_debug_trigger():
    """Debug endpoint — writes a test canvas and broadcasts to all connected frontends."""
    from backend.system.canvas import write_canvas_state
    from backend.api.websocket.manager import manager
    session_id = "debug_session"
    test_html = """<!DOCTYPE html><html><head><meta charset='UTF-8'>
    <style>body{margin:0;background:#0f0f1a;display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;}
    .box{background:linear-gradient(135deg,#667eea,#764ba2);padding:40px 60px;border-radius:20px;text-align:center;color:white;box-shadow:0 20px 60px rgba(102,126,234,0.4);}
    h1{font-size:2rem;margin:0 0 10px;}p{opacity:0.8;margin:0;}</style></head>
    <body><div class='box'><h1>✅ Canvas Works!</h1><p>WebSocket + Canvas pipeline সফলভাবে কাজ করছে।</p></div></body></html>"""
    write_canvas_state(session_id, test_html)
    await manager.broadcast_event("canvas_update", {"session_id": session_id})
    connected = len(manager.active_connections)
    return {"status": "ok", "session_id": session_id, "connected_clients": connected,
            "canvas_url": f"http://127.0.0.1:8000/canvas/{session_id}/index.html"}


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

def voice_stats():
    """Debug endpoint — voice engine latency ring buffer (last 1000 requests)."""
    try:
        from backend.voice.voice_state_machine import voice_state_machine
        return {"status": "ok", **voice_state_machine.get_stats()}
    except Exception as e:
        return {"status": "error", "message": str(e)}


if _DEBUG_ROUTES_ENABLED:
    app.add_api_route(
        "/canvas/debug/trigger",
        canvas_debug_trigger,
        methods=["POST"],
        include_in_schema=False,
    )
    app.add_api_route("/skills", list_skills, methods=["GET"], include_in_schema=False)
    app.add_api_route("/voice/stats", voice_stats, methods=["GET"], include_in_schema=False)
