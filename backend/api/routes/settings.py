from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ...database.connection import get_db
from ...database.models import UserPreferences
from ...database.crypto import crypto_manager
import logging
import httpx
import os

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/settings", tags=["settings"])


class KeysPayload(BaseModel):
    gemini_key: str | None = None
    provider: str | None = None
    elevenlabs_key: str | None = None
    elevenlabs_voice_id: str | None = None
    elevenlabs_model_id: str | None = None
    tts_primary_provider: str | None = None

class PermissionsPayload(BaseModel):
    browser: bool | None = None
    filesystem: bool | None = None
    terminal: bool | None = None
    system: bool | None = None
    auto_approve: bool | None = None
    web_search: bool | None = None


def _save_pref(db: Session, key: str, value: str):
    """Upsert a UserPreferences record with encrypted value."""
    encrypted = crypto_manager.encrypt(value)
    pref = db.query(UserPreferences).filter(UserPreferences.key == key).first()
    if pref:
        pref.value = encrypted
    else:
        db.add(UserPreferences(key=key, value=encrypted))


# ── Status ────────────────────────────────────────────────────────────────────

@router.get("/status")
def get_status(db: Session = Depends(get_db)):
    """Returns boolean status of keys."""
    gemini_pref = db.query(UserPreferences).filter(UserPreferences.key == "GEMINI_API_KEY").first()
    elevenlabs_pref = db.query(UserPreferences).filter(UserPreferences.key == "ELEVENLABS_API_KEY").first()
    voice_pref = db.query(UserPreferences).filter(UserPreferences.key == "ELEVENLABS_VOICE_ID").first()
    model_pref = db.query(UserPreferences).filter(UserPreferences.key == "ELEVENLABS_MODEL_ID").first()

    voice_id = ""
    if voice_pref and voice_pref.value:
        try:
            voice_id = crypto_manager.decrypt(voice_pref.value)
        except:
            pass

    model_id = ""
    if model_pref and model_pref.value:
        try:
            model_id = crypto_manager.decrypt(model_pref.value)
        except:
            pass

    # Retrieve active primary voice provider
    tts_provider_pref = db.query(UserPreferences).filter(UserPreferences.key == "TTS_PRIMARY_PROVIDER").first()
    tts_primary_provider = ""
    if tts_provider_pref and tts_provider_pref.value:
        try:
            tts_primary_provider = crypto_manager.decrypt(tts_provider_pref.value).strip()
        except:
            pass
    if not tts_primary_provider:
        if elevenlabs_pref and elevenlabs_pref.value:
            tts_primary_provider = "elevenlabs"
        else:
            tts_primary_provider = "edge"

    # Permissions
    def _is_enabled(k: str) -> bool:
        p = db.query(UserPreferences).filter(UserPreferences.key == k).first()
        if p and p.value:
            try:
                return crypto_manager.decrypt(p.value) == "true"
            except:
                pass
        return False

    return {
        "gemini_configured": bool(gemini_pref and gemini_pref.value),
        "elevenlabs_configured": bool(elevenlabs_pref and elevenlabs_pref.value),
        "elevenlabs_voice_id": voice_id,
        "elevenlabs_model_id": model_id,
        "tts_primary_provider": tts_primary_provider,
        "permissions": {
            "browser": _is_enabled("PERM_BROWSER"),
            "filesystem": _is_enabled("PERM_FILESYSTEM"),
            "terminal": _is_enabled("PERM_TERMINAL"),
            "system": _is_enabled("PERM_SYSTEM"),
            "auto_approve": _is_enabled("PERM_AUTO_APPROVE"),
            "web_search": _is_enabled("PERM_WEB_SEARCH"),
        }
    }


@router.post("/test-key")
def test_gemini_key(payload: KeysPayload):
    """Validates the Gemini or ElevenLabs key by attempting a lightweight generation or connection check."""
    if payload.elevenlabs_key:
        clean_key = payload.elevenlabs_key.strip()
        
        # cvoice.ai Validation
        if clean_key.startswith("cvai_"):
            url = "https://cvoice.ai/api/me"
            headers = {
                "X-API-Key": clean_key
            }
            try:
                response = httpx.get(url, headers=headers, timeout=10.0)
                response.raise_for_status()
                return {"status": "success", "message": "cvoice.ai Key is valid.", "provider": "cvoice"}
            except Exception as e:
                logger.error(f"cvoice.ai validation failed: {e}")
                raise HTTPException(status_code=401, detail=f"Validation failed for cvoice.ai key: {e}")
                
        # ElevenLabs Validation
        url = "https://api.elevenlabs.io/v1/voices"
        headers = {
            "xi-api-key": clean_key
        }
        try:
            response = httpx.get(url, headers=headers, timeout=10.0)
            response.raise_for_status()
            return {"status": "success", "message": "ElevenLabs Key is valid.", "provider": "elevenlabs"}
        except Exception as e:
            logger.error(f"ElevenLabs validation failed: {e}")
            raise HTTPException(status_code=401, detail=f"Validation failed for ElevenLabs key: {e}")

    if not payload.gemini_key:
        raise HTTPException(status_code=400, detail="Key required")
    clean_key = payload.gemini_key.strip()
    
    # 1. OpenRouter
    if clean_key.startswith("sk-or-"):
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {clean_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:1420",
            "X-Title": "Maya AI"
        }
        payload_data = {
            "model": "google/gemini-2.5-flash",
            "messages": [{"role": "user", "content": "Ping"}],
            "max_tokens": 5
        }
        try:
            response = httpx.post(url, headers=headers, json=payload_data, timeout=10.0)
            response.raise_for_status()
            return {"status": "success", "message": "OpenRouter Key is valid and active.", "provider": "openrouter"}
        except Exception as e:
            logger.error(f"OpenRouter validation failed: {e}")
            raise HTTPException(status_code=401, detail=f"Validation failed for OpenRouter key: {e}")
            
    # 2. NVIDIA NIM
    elif clean_key.startswith("nvapi-"):
        url = "https://integrate.api.nvidia.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {clean_key}",
            "Content-Type": "application/json"
        }
        payload_data = {
            "model": "meta/llama-3.1-8b-instruct",
            "messages": [{"role": "user", "content": "Ping"}],
            "max_tokens": 5
        }
        try:
            response = httpx.post(url, headers=headers, json=payload_data, timeout=10.0)
            response.raise_for_status()
            return {"status": "success", "message": "NVIDIA NIM Key is valid and active.", "provider": "nvidia"}
        except Exception as e:
            logger.error(f"NVIDIA NIM validation failed: {e}")
            raise HTTPException(status_code=401, detail=f"Validation failed for NVIDIA NIM key: {e}")
            
    # 3 & 4. OpenCode Zen or OpenAI
    elif clean_key.startswith("sk-"):
        # Let's try both endpoints to see which one accepts this key.
        # We determine the order of trying based on key length (OpenCode Zen is typically 67 chars).
        is_likely_zen = (len(clean_key) == 67)
        errors = []
        
        def try_zen():
            url = "https://opencode.ai/zen/v1/models"
            headers = {
                "Authorization": f"Bearer {clean_key}",
                "Content-Type": "application/json"
            }
            res = httpx.get(url, headers=headers, timeout=10.0)
            res.raise_for_status()
            return {"status": "success", "message": "OpenCode Zen Key is valid and active.", "provider": "opencode_zen"}

        def try_openai():
            url = "https://api.openai.com/v1/models"
            headers = {
                "Authorization": f"Bearer {clean_key}",
                "Content-Type": "application/json"
            }
            res = httpx.get(url, headers=headers, timeout=10.0)
            res.raise_for_status()
            return {"status": "success", "message": "OpenAI Key is valid and active.", "provider": "openai"}

        order = [try_zen, try_openai] if is_likely_zen else [try_openai, try_zen]
        
        for func in order:
            try:
                return func()
            except Exception as e:
                errors.append(f"{func.__name__} failed: {e}")
                
        # If both failed
        logger.error(f"Validation failed for sk- key: {errors}")
        raise HTTPException(status_code=401, detail=f"Validation failed for sk- key: {'; '.join(errors)}")
            
    # 5. Native Google Gemini Key
    else:
        try:
            from google import genai
            client = genai.Client(api_key=clean_key)
            models_to_try = [
                'gemini-3.5-flash',
                'gemini-2.5-flash',
                'gemini-3.1-flash-lite',
                'gemini-1.5-flash'
            ]
            response = None
            last_error = None
            for model in models_to_try:
                try:
                    response = client.models.generate_content(
                        model=model,
                        contents='Ping'
                    )
                    if response and response.text:
                        logger.info(f"Successfully validated key using model: {model}")
                        break
                except Exception as e:
                    logger.warning(f"Failed key validation with model {model}: {e}")
                    last_error = e
            
            if response and response.text:
                return {"status": "success", "message": "Key is valid and active.", "provider": "gemini"}
            
            if last_error:
                raise last_error
            raise Exception("Failed to generate content with any model.")
        except Exception as e:
            logger.error(f"Key validation failed: {e}")
            err_msg = str(e)
            if "API key expired" in err_msg or "400" in err_msg:
                err_msg = "API key expired. Please renew/regenerate your API key on Google AI Studio."
            raise HTTPException(status_code=401, detail=f"Validation failed: {err_msg}")


# ── Save Keys ─────────────────────────────────────────────────────────────────

from fastapi import BackgroundTasks

def _reload_adapters():
    try:
        from ...brain.providers.gemini_adapter import gemini_adapter
        gemini_adapter.reload_key()
    except Exception as e:
        logger.error(f"Gemini reload failed: {e}")
    try:
        from ...voice.output.tts_router import tts_router
        tts_router.reload_key()
    except Exception as e:
        logger.error(f"TTS reload failed: {e}")

@router.post("/keys")
def save_keys(payload: KeysPayload, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Encrypts and saves API keys. Reloads adapters immediately in background."""
    if payload.gemini_key:
        key = payload.gemini_key.strip()
        _save_pref(db, "GEMINI_API_KEY", key)
        
        provider = payload.provider
        if not provider:
            if key.startswith("sk-or-"):
                provider = "openrouter"
            elif key.startswith("nvapi-"):
                provider = "nvidia"
            elif key.startswith("sk-"):
                if len(key) == 67:
                    provider = "opencode_zen"
                else:
                    provider = "openai"
            else:
                provider = "gemini"
        _save_pref(db, "GEMINI_API_PROVIDER", provider)

    if payload.elevenlabs_key is not None:
        _save_pref(db, "ELEVENLABS_API_KEY", payload.elevenlabs_key.strip())
    if payload.elevenlabs_voice_id is not None:
        _save_pref(db, "ELEVENLABS_VOICE_ID", payload.elevenlabs_voice_id.strip())
    if payload.elevenlabs_model_id is not None:
        _save_pref(db, "ELEVENLABS_MODEL_ID", payload.elevenlabs_model_id.strip())
    if payload.tts_primary_provider is not None:
        _save_pref(db, "TTS_PRIMARY_PROVIDER", payload.tts_primary_provider.strip())
        
    db.commit()

    # Hot-reload in background to prevent request hanging or db locking
    background_tasks.add_task(_reload_adapters)

    return {"status": "success"}

# ── Save Permissions ──────────────────────────────────────────────────────────

@router.post("/permissions")
def save_permissions(payload: PermissionsPayload, db: Session = Depends(get_db)):
    """Saves system control permissions."""
    if payload.browser is not None:
        _save_pref(db, "PERM_BROWSER", "true" if payload.browser else "false")
    if payload.filesystem is not None:
        _save_pref(db, "PERM_FILESYSTEM", "true" if payload.filesystem else "false")
    if payload.terminal is not None:
        _save_pref(db, "PERM_TERMINAL", "true" if payload.terminal else "false")
    if payload.system is not None:
        _save_pref(db, "PERM_SYSTEM", "true" if payload.system else "false")
    if payload.auto_approve is not None:
        _save_pref(db, "PERM_AUTO_APPROVE", "true" if payload.auto_approve else "false")
    if payload.web_search is not None:
        _save_pref(db, "PERM_WEB_SEARCH", "true" if payload.web_search else "false")
    
    db.commit()
    return {"status": "success"}


# ── Telegram Settings ─────────────────────────────────────────────────────────

class TelegramSettingsPayload(BaseModel):
    enabled: bool | None = None
    bot_token: str | None = None

@router.get("/telegram")
def get_telegram_settings(db: Session = Depends(get_db)):
    """Returns Telegram configuration and pairing status."""
    pref_enabled = db.query(UserPreferences).filter(UserPreferences.key == "TELEGRAM_BOT_ENABLED").first()
    pref_token = db.query(UserPreferences).filter(UserPreferences.key == "TELEGRAM_BOT_TOKEN").first()
    pref_chat = db.query(UserPreferences).filter(UserPreferences.key == "TELEGRAM_CHAT_ID").first()
    pref_code = db.query(UserPreferences).filter(UserPreferences.key == "TELEGRAM_PAIRING_CODE").first()

    enabled = False
    if pref_enabled and pref_enabled.value:
        decrypted = crypto_manager.decrypt(pref_enabled.value)
        val = decrypted if (decrypted or not pref_enabled.value) else pref_enabled.value
        enabled = (val == "true")
        
    token_configured = bool(pref_token and pref_token.value)
    
    paired = False
    chat_id_val = None
    if pref_chat and pref_chat.value:
        decrypted = crypto_manager.decrypt(pref_chat.value)
        chat_id_val = decrypted if (decrypted or not pref_chat.value) else pref_chat.value
        paired = bool(chat_id_val)

    # If code is missing, generate one
    import random
    code_val = None
    if pref_code and pref_code.value:
        decrypted = crypto_manager.decrypt(pref_code.value)
        code_val = decrypted if (decrypted or not pref_code.value) else pref_code.value
        
    if not code_val:
        code_val = str(random.randint(100000, 999999))
        _save_pref(db, "TELEGRAM_PAIRING_CODE", code_val)
        db.commit()

    return {
        "enabled": enabled,
        "token_configured": token_configured,
        "paired": paired,
        "chat_id": chat_id_val,
        "pairing_code": code_val
    }

@router.post("/telegram")
def save_telegram_settings(payload: TelegramSettingsPayload, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Saves Telegram bot settings and restarts the service in the background."""
    if payload.enabled is not None:
        _save_pref(db, "TELEGRAM_BOT_ENABLED", "true" if payload.enabled else "false")
    
    if payload.bot_token is not None:
        token = payload.bot_token.strip()
        # Only overwrite if it's not the masked dummy token from UI
        if token and not token.startswith("•"):
            _save_pref(db, "TELEGRAM_BOT_TOKEN", token)
            # Reset pairing if bot token changes
            pref_chat = db.query(UserPreferences).filter(UserPreferences.key == "TELEGRAM_CHAT_ID").first()
            if pref_chat:
                db.delete(pref_chat)
        elif not token:
            pref_token = db.query(UserPreferences).filter(UserPreferences.key == "TELEGRAM_BOT_TOKEN").first()
            if pref_token:
                db.delete(pref_token)
            _save_pref(db, "TELEGRAM_BOT_ENABLED", "false")

    db.commit()

    def _restart_bot():
        try:
            from backend.api.telegram_bot import telegram_bot_manager
            telegram_bot_manager.restart()
        except Exception as e:
            logger.error(f"Failed to restart Telegram bot: {e}")

    background_tasks.add_task(_restart_bot)
    return {"status": "success"}

@router.post("/telegram/reset")
def reset_telegram_pairing(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Resets the paired Telegram account."""
    pref_chat = db.query(UserPreferences).filter(UserPreferences.key == "TELEGRAM_CHAT_ID").first()
    if pref_chat:
        db.delete(pref_chat)
    
    # Generate new pairing code
    import random
    code = str(random.randint(100000, 999999))
    _save_pref(db, "TELEGRAM_PAIRING_CODE", code)
    
    db.commit()

    def _restart_bot():
        try:
            from backend.api.telegram_bot import telegram_bot_manager
            telegram_bot_manager.restart()
        except Exception as e:
            logger.error(f"Failed to restart Telegram bot: {e}")

    background_tasks.add_task(_restart_bot)
    return {"status": "success"}


# End of file
