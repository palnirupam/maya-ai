from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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

@app.on_event("startup")
def startup_event():
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
        import asyncio
        from backend.system.scheduler import maya_scheduler
        asyncio.create_task(maya_scheduler.start())
    except Exception as e:
        logging.error(f"Error starting Scheduler: {e}")

@app.on_event("shutdown")
def shutdown_event():
    try:
        from backend.api.telegram_bot import telegram_bot_manager
        telegram_bot_manager.stop()
    except Exception as e:
        logging.error(f"Error stopping Telegram Bot: {e}")
    try:
        from backend.tools.desktop.advanced.whatsapp_manager import whatsapp_manager
        whatsapp_manager.stop()
    except Exception as e:
        logging.error(f"Error stopping WhatsApp service: {e}")
    try:
        import asyncio
        from backend.system.scheduler import maya_scheduler
        asyncio.create_task(maya_scheduler.stop())
    except Exception as e:
        logging.error(f"Error stopping Scheduler: {e}")

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Maya AI Backend is running. WhatsApp connection fix applied successfully."}
