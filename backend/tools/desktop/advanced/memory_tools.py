from ....database.connection import SessionLocal
from ....database.models import UserPreferences, LongTermMemory
from ....database.crypto import crypto_manager
from ....brain.memory.long_term_memory import store_memory, retrieve_relevant_memories
import json

def remember_fact(topic: str, fact: str, importance: int = 3) -> str:
    """
    Stores a fact about the user or a topic into long-term persistent memory.
    Use this to remember preferences, context, or details the user tells you.
    """
    success = store_memory(category=topic, content=fact, importance=importance)
    if success:
        return f"SUCCESS: Remembered fact about {topic}."
    return f"ERROR: Failed to remember fact."

def recall_facts(category: str = None) -> str:
    """
    Retrieves all facts stored in long-term persistent memory.
    Use this to recall details about the user or past topics.
    """
    memories = retrieve_relevant_memories(active_category=category)
    if not memories:
        return "No facts remembered yet."
    return "Remembered Facts:\n" + "\n".join([f"- {m}" for m in memories])

def forget_fact(topic: str) -> str:
    """
    Forgets a specific fact or topic from long-term memory.
    """
    db = SessionLocal()
    try:
        topic_lower = topic.lower()
        memories = db.query(LongTermMemory).all()
        deleted_count = 0
        for mem in memories:
            try:
                decrypted_category = crypto_manager.decrypt(mem.category)
                if decrypted_category == topic_lower:
                    db.delete(mem)
                    deleted_count += 1
            except:
                pass
        db.commit()
        if deleted_count > 0:
            return f"SUCCESS: Forgot {deleted_count} facts about {topic}."
        return f"No facts found about {topic}."
    except Exception as e:
        return f"ERROR: Failed to forget fact. {e}"
    finally:
        db.close()


def configure_gmail_credentials(email: str, app_password: str) -> str:
    """
    Securely encrypts and saves the user's Gmail address and 16-letter App Password into the database.
    Use this when the user wants to configure or update their Gmail credentials for background email sending.
    Args:
        email (str): The Gmail address (e.g. user@gmail.com).
        app_password (str): The 16-letter App Password generated from Google settings (e.g. abcd efgh ijkl mnop).
    """
    db = SessionLocal()
    try:
        # Clean password (remove spaces) and email
        clean_pass = app_password.replace(" ", "").lower().strip()
        clean_email = email.lower().strip()
        
        email_val = crypto_manager.encrypt(clean_email)
        pass_val = crypto_manager.encrypt(clean_pass)
        
        # Save email
        email_pref = db.query(UserPreferences).filter(UserPreferences.key == "GMAIL_EMAIL").first()
        if email_pref:
            email_pref.value = email_val
        else:
            db.add(UserPreferences(key="GMAIL_EMAIL", value=email_val))
            
        # Save password
        pass_pref = db.query(UserPreferences).filter(UserPreferences.key == "GMAIL_APP_PASSWORD").first()
        if pass_pref:
            pass_pref.value = pass_val
        else:
            db.add(UserPreferences(key="GMAIL_APP_PASSWORD", value=pass_val))
            
        db.commit()
        return "SUCCESS: Gmail credentials securely configured. Maya can now send background emails!"
    except Exception as e:
        return f"ERROR: Failed to save credentials. {e}"
    finally:
        db.close()


def schedule_reminder(message: str, hours_from_now: float = 0, notify_channel: str = "chat_message") -> str:
    """
    Schedules a reminder to be sent after a certain number of hours.
    Args:
        message (str): The reminder message.
        hours_from_now (float): Hours from now to trigger the reminder (e.g., 0.16 for ~10 mins).
        notify_channel (str): Either 'chat_message' or 'gui_popup'.
    """
    db = SessionLocal()
    try:
        from datetime import datetime, timedelta, timezone
        from ....database.models import ScheduledTask
        import json
        
        payload = crypto_manager.encrypt(json.dumps({"message": message}))
        name = crypto_manager.encrypt("User Reminder")
        next_run = datetime.now(timezone.utc) + timedelta(hours=hours_from_now)
        
        task = ScheduledTask(
            name=name,
            task_type="REMINDER",
            task_payload=payload,
            next_run=next_run,
            notify_channel=notify_channel
        )
        db.add(task)
        db.commit()
        return f"SUCCESS: Reminder scheduled for {next_run.strftime('%Y-%m-%d %H:%M:%S UTC')}."
    except Exception as e:
        return f"ERROR: Failed to schedule reminder. {e}"
    finally:
        db.close()
