import asyncio
import httpx
import logging
import json
from datetime import datetime, timezone, timedelta
from ..database.connection import SessionLocal
from ..database.models import ScheduledTask
from ..database.crypto import crypto_manager
from ..brain.memory.long_term_memory import cleanup_expired_memories

logger = logging.getLogger(__name__)

class MayaScheduler:
    def __init__(self):
        self.is_running = False
        self._task_task = None
        self.last_cleanup = None

    async def start(self):
        if self.is_running:
            return
        self.is_running = True
        self._task_task = asyncio.create_task(self._scheduler_loop())
        logger.info("Maya Scheduler started.")

    async def stop(self):
        self.is_running = False
        if self._task_task:
            self._task_task.cancel()
            try:
                await self._task_task
            except asyncio.CancelledError:
                pass
        logger.info("Maya Scheduler stopped.")

    async def _scheduler_loop(self):
        while self.is_running:
            try:
                now = datetime.now(timezone.utc)
                
                # Daily memory cleanup
                if not self.last_cleanup or (now - self.last_cleanup).days >= 1:
                    cleanup_expired_memories()
                    self.last_cleanup = now

                db = SessionLocal()
                try:
                    tasks = db.query(ScheduledTask).filter(ScheduledTask.is_active == 1).all()
                    for task in tasks:
                        if task.next_run and task.next_run <= now:
                            await self._execute_task(task, db)
                finally:
                    db.close()
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")
                
            await asyncio.sleep(60)

    async def _execute_task(self, task: ScheduledTask, db):
        try:
            task_type = task.task_type
            payload = {}
            if task.task_payload:
                try:
                    decrypted_payload = crypto_manager.decrypt(task.task_payload)
                    payload = json.loads(decrypted_payload)
                except Exception as e:
                    logger.error(f"Failed to decrypt task payload {task.id}: {e}")
            
            message = ""
            if task_type == "DAILY_GREETING":
                message = "Good morning! Have a wonderful day!"
            elif task_type == "REMINDER":
                message = payload.get("message", "Reminder!")
            elif task_type == "WEATHER_CHECK":
                try:
                    async with httpx.AsyncClient() as client:
                        resp = await client.get("https://wttr.in/?format=j1", timeout=10)
                        data = resp.json()
                        temp = data["current_condition"][0]["temp_C"]
                        desc = data["current_condition"][0]["weatherDesc"][0]["value"]
                        message = f"Weather Update: It is {temp}°C and {desc}."
                except Exception as e:
                    logger.error(f"Failed to fetch weather: {e}")
                    message = "Weather Update: Failed to fetch data."
            
            # Dispatch
            if task.notify_channel == "chat_message":
                from ..api.telegram_bot import telegram_bot_manager
                if telegram_bot_manager and telegram_bot_manager.application:
                    from ..database.models import UserPreferences
                    chat_id_pref = db.query(UserPreferences).filter(UserPreferences.key == "TELEGRAM_CHAT_ID").first()
                    if chat_id_pref and chat_id_pref.value:
                        try:
                            chat_id = crypto_manager.decrypt(chat_id_pref.value)
                            if not chat_id:
                                chat_id = chat_id_pref.value
                            asyncio.create_task(telegram_bot_manager.application.bot.send_message(chat_id=chat_id, text=message))
                        except Exception as e:
                            logger.error(f"Failed to send to telegram: {e}")
            elif task.notify_channel == "gui_popup":
                pass

            task.last_run = datetime.now(timezone.utc)
            if not task.cron_expression:
                task.is_active = 0
            else:
                if task.cron_expression == "@daily":
                    task.next_run = task.next_run + timedelta(days=1)
                else:
                    task.is_active = 0
            
            db.commit()
            
        except Exception as e:
            logger.error(f"Error executing task {task.id}: {e}")

maya_scheduler = MayaScheduler()
