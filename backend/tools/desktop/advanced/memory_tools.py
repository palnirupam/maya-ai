from ....database.connection import SessionLocal
from ....database.models import UserPreferences, LongTermMemory
from ....database.crypto import crypto_manager
from ....brain.memory.long_term_memory import store_memory, retrieve_relevant_memories
import json
import os
import re
from pathlib import Path

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
            except Exception as e:
                logger.warning("Failed to decrypt memory category for memory id=%s: %s", mem.id, e)
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
    from backend.tools.desktop.advanced.email_security import validate_gmail_credentials

    credentials, validation_error = validate_gmail_credentials(email, app_password)
    if validation_error or credentials is None:
        return f"ERROR: {validation_error}"
    clean_email, clean_pass = credentials

    db = SessionLocal()
    try:
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
        return "SUCCESS: Gmail credentials securely configured."
    except Exception as exc:
        db.rollback()
        import logging

        logging.getLogger(__name__).warning(
            "Gmail credential save failed (%s).", type(exc).__name__
        )
        return "ERROR: Gmail credentials could not be saved."
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


def configure_mcp_server(server_name: str, npm_package: str, env_vars: dict = None) -> str:
    """
    Securely configures an MCP server for Maya by updating the mcp_servers.json configuration file.
    Use this when the user asks to add or update an MCP server, API key, or integration (e.g., youtube, google drive).
    """
    # Security Validations
    if not re.match(r"^[a-z0-9_-]+$", server_name):
        return "ERROR: Invalid server_name. Must be lowercase alphanumeric with hyphens or underscores only."
        
    if not re.match(r"^(@[a-z0-9._-]+/)?(?!\.)[a-z0-9._-]+$", npm_package):
        return "ERROR: Invalid npm_package. Unsafe characters detected."
        
    env_vars = env_vars or {}
    for k, v in env_vars.items():
        if not re.match(r"^[A-Z_][A-Z0-9_]*$", k):
            return f"ERROR: Invalid environment variable key '{k}'."
        # Check for harmful content in value
        if any(bad in v for bad in ("\n", "\r", "%0a", "\x00", "$(", "`")):
            return f"ERROR: Invalid character in environment variable value for '{k}'."

    # Config Path
    config_path = Path(__file__).parent.parent.parent.parent / "config" / "mcp_servers.json"
    
    # Read existing config
    config = {"mcpServers": {}}
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            pass # fallback to default

    if "mcpServers" not in config or not isinstance(config["mcpServers"], dict):
        config["mcpServers"] = {}

    # Hardcoded Templating (No raw JSON merging)
    config["mcpServers"][server_name] = {
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", npm_package],
        "env": env_vars
    }
    
    # Atomic File Write
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = config_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        os.replace(tmp_path, config_path)
        return f"SUCCESS: MCP Server '{server_name}' securely configured. Please restart Maya for changes to take effect."
    except Exception as e:
        return f"ERROR: Failed to save MCP configuration: {str(e)}"
