from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session
import os
from ...database.connection import get_db
from ...database.models import UserPreferences
from ...database.crypto import crypto_manager
from ...database.preferences import (
    decrypt_pref_value as _decrypt_stored_pref,
    read_permission_pref,
)
from ...config.model_config import get_model
from ...config.provider_config import (
    ANTHROPIC_KIND,
    OPENAI_COMPATIBLE_KIND,
    base_url_from_env,
    chat_url_for_provider,
    detect_provider_from_key,
    model_from_env,
    model_for_provider,
    normalize_provider,
    provider_options,
    provider_from_env,
    provider_spec,
)
import logging
import httpx

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/settings", tags=["settings"])


class RecoveryPayload(BaseModel):
    old_key: str | None = None

def _model_for_provider(provider: str, stored_model: str | None) -> str:
    return model_for_provider(provider, stored_model, get_model)


def _decrypt_pref_value(pref) -> str:
    return _decrypt_stored_pref(pref)


def _provider_headers(provider: str, api_key: str) -> dict[str, str]:
    spec = provider_spec(provider)
    if spec.kind == ANTHROPIC_KIND:
        return {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if normalize_provider(provider) == "openrouter":
        headers["HTTP-Referer"] = "http://localhost:1420"
        headers["X-Title"] = "Maya AI"
    return headers


def _validate_provider_key(provider: str, api_key: str, base_url: str | None, model: str | None) -> dict:
    provider = normalize_provider(provider)
    spec = provider_spec(provider)
    active_model = _model_for_provider(provider, model)

    if spec.kind == ANTHROPIC_KIND:
        payload_data = {
            "model": active_model,
            "messages": [{"role": "user", "content": "Ping"}],
            "max_tokens": 5,
        }
        response = httpx.post(spec.api_url, headers=_provider_headers(provider, api_key), json=payload_data, timeout=10.0)
        response.raise_for_status()
        return {"status": "success", "message": f"{spec.label} key is valid.", "provider": provider}

    if spec.kind == OPENAI_COMPATIBLE_KIND:
        if spec.models_url:
            response = httpx.get(spec.models_url, headers=_provider_headers(provider, api_key), timeout=10.0)
            response.raise_for_status()
            return {"status": "success", "message": f"{spec.label} key is valid.", "provider": provider}

        chat_url = chat_url_for_provider(provider, base_url)
        if not chat_url:
            raise HTTPException(
                status_code=400,
                detail=f"{spec.label} requires a base URL. For Cloudflare use https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/ai",
            )
        payload_data = {
            "model": active_model,
            "messages": [{"role": "user", "content": "Ping"}],
            "max_tokens": 5,
        }
        response = httpx.post(chat_url, headers=_provider_headers(provider, api_key), json=payload_data, timeout=10.0)
        response.raise_for_status()
        return {"status": "success", "message": f"{spec.label} key is valid.", "provider": provider}

    # Native Google Gemini key.
    from google import genai

    client = genai.Client(api_key=api_key)
    models_to_try = [
        active_model,
        'gemini-3.5-flash',
        'gemini-3.1-flash-lite',
        'gemini-2.5-flash-lite',
        'gemini-2.5-flash',
        'gemini-2.0-flash',
        'gemini-1.5-flash',
    ]
    seen = set()
    last_error = None
    for model_name in models_to_try:
        if not model_name or model_name in seen:
            continue
        seen.add(model_name)
        try:
            response = client.models.generate_content(model=model_name, contents='Ping')
            if response and response.text:
                logger.info(f"Successfully validated key using model: {model_name}")
                return {"status": "success", "message": "Key is valid and active.", "provider": "gemini"}
        except Exception as e:
            logger.warning(
                "Key validation failed for model %s (%s).",
                model_name,
                type(e).__name__,
            )
            last_error = e

    if last_error:
        raise last_error
    raise Exception("Failed to generate content with any model.")


class KeysPayload(BaseModel):
    gemini_key: str | None = None
    provider: str | None = None
    base_url: str | None = None
    active_model: str | None = None
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

@router.get("/status/app")
def get_app_status(db: Session = Depends(get_db)):
    """Compatibility endpoint expected by the frontend recovery flow."""
    try:
        from ...database.crypto import KeyUnreadableError
    except Exception:
        KeyUnreadableError = Exception

    try:
        # If any stored preference cannot be decrypted with the current key, the
        # app should surface the recovery modal to let the user provide a legacy key.
        gemini_pref = db.query(UserPreferences).filter(UserPreferences.key == "GEMINI_API_KEY").first()
        if gemini_pref and gemini_pref.value:
            crypto_manager.decrypt(gemini_pref.value, raise_on_failure=True)
        elevenlabs_pref = db.query(UserPreferences).filter(UserPreferences.key == "ELEVENLABS_API_KEY").first()
        if elevenlabs_pref and elevenlabs_pref.value:
            crypto_manager.decrypt(elevenlabs_pref.value, raise_on_failure=True)
    except KeyUnreadableError:
        return {"recovery_required": True, "detail": "Stored credentials are unreadable with the current key."}
    except Exception:
        # Conservatively return false unless the current crypto layer explicitly flags a mismatch.
        pass

    return {"recovery_required": False}


@router.post("/recover")
def recover_from_legacy_key(payload: RecoveryPayload, db: Session = Depends(get_db)):
    """Recover encrypted preferences using a legacy Fernet key provided by the user."""
    old_key = (payload.old_key or "").strip()
    if not old_key:
        raise HTTPException(status_code=400, detail="A legacy key is required.")

    from cryptography.fernet import Fernet, InvalidToken

    try:
        legacy_cipher = Fernet(old_key)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid legacy key format: {exc}") from exc

    # Attempt to re-encrypt any stored preference that is still readable with the legacy key.
    prefs = db.query(UserPreferences).all()
    migrated = 0
    for pref in prefs:
        if not pref.value:
            continue
        try:
            plaintext = crypto_manager.decrypt(pref.value, raise_on_failure=False)
            if plaintext:
                # If the current manager can already read it, nothing to do.
                continue
        except Exception:
            pass

        try:
            legacy_plaintext = legacy_cipher.decrypt(pref.value.encode("utf-8")).decode("utf-8")
        except (InvalidToken, ValueError, TypeError):
            continue

        try:
            pref.value = crypto_manager.encrypt(legacy_plaintext)
            migrated += 1
        except Exception as exc:
            logger.warning("Failed to re-encrypt preference %s during recovery: %s", pref.key, exc)

    db.commit()
    if migrated:
        return {"status": "success", "migrated": migrated, "message": "Recovered encrypted preferences using the provided legacy key."}
    return {"status": "success", "migrated": 0, "message": "No encrypted preferences were recovered with the provided key."}


@router.get("/status")
def get_status(db: Session = Depends(get_db)):
    """Returns boolean status of keys."""
    gemini_pref = db.query(UserPreferences).filter(UserPreferences.key == "GEMINI_API_KEY").first()
    elevenlabs_pref = db.query(UserPreferences).filter(UserPreferences.key == "ELEVENLABS_API_KEY").first()
    voice_pref = db.query(UserPreferences).filter(UserPreferences.key == "ELEVENLABS_VOICE_ID").first()
    model_pref = db.query(UserPreferences).filter(UserPreferences.key == "ELEVENLABS_MODEL_ID").first()
    active_model_pref = db.query(UserPreferences).filter(UserPreferences.key == "GEMINI_ACTIVE_MODEL").first()
    provider_pref = db.query(UserPreferences).filter(UserPreferences.key == "GEMINI_API_PROVIDER").first()
    base_url_pref = db.query(UserPreferences).filter(UserPreferences.key == "GEMINI_API_BASE_URL").first()

    voice_id = _decrypt_pref_value(voice_pref)
    model_id = _decrypt_pref_value(model_pref)
    active_model = _decrypt_pref_value(active_model_pref)
    raw_provider = _decrypt_pref_value(provider_pref)
    provider = normalize_provider(raw_provider) if raw_provider else ""
    base_url = _decrypt_pref_value(base_url_pref)
    env_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    env_provider = provider_from_env()
    env_model = model_from_env()
    env_base_url = base_url_from_env()

    if env_provider:
        provider = env_provider
    elif not provider and gemini_pref and gemini_pref.value:
        try:
            key_hint = crypto_manager.decrypt(gemini_pref.value).strip()
            if key_hint:
                provider = detect_provider_from_key(key_hint)
        except Exception as e:
            logger.warning("Failed to decrypt gemini provider preference: %s", e)
    if not provider and env_key:
        provider = detect_provider_from_key(env_key)
    if not provider:
        provider = "gemini"
    active_model = _model_for_provider(provider, env_model or (None if env_provider else active_model))
    base_url = env_base_url or base_url

    # Retrieve active primary voice provider
    tts_provider_pref = db.query(UserPreferences).filter(UserPreferences.key == "TTS_PRIMARY_PROVIDER").first()
    tts_primary_provider = ""
    if tts_provider_pref and tts_provider_pref.value:
        try:
            tts_primary_provider = crypto_manager.decrypt(tts_provider_pref.value).strip()
        except Exception as e:
            logger.warning("Failed to decrypt TTS provider preference: %s", e)
    if not tts_primary_provider:
        tts_primary_provider = "edge"

    # Permissions
    return {
        "gemini_configured": bool((gemini_pref and gemini_pref.value) or env_key),
        "gemini_provider": provider,
        "gemini_active_model": active_model,
        "gemini_base_url": base_url,
        "provider_options": provider_options(get_model),
        "elevenlabs_configured": bool(elevenlabs_pref and elevenlabs_pref.value),
        "elevenlabs_voice_id": voice_id,
        "elevenlabs_model_id": model_id,
        "tts_primary_provider": tts_primary_provider,
        "permissions": {
            "browser": read_permission_pref(db, "PERM_BROWSER"),
            "filesystem": read_permission_pref(db, "PERM_FILESYSTEM"),
            "terminal": read_permission_pref(db, "PERM_TERMINAL"),
            "system": read_permission_pref(db, "PERM_SYSTEM"),
            "auto_approve": read_permission_pref(db, "PERM_AUTO_APPROVE"),
            "web_search": read_permission_pref(db, "PERM_WEB_SEARCH"),
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
                logger.warning("cvoice.ai validation failed (%s).", type(e).__name__)
                raise HTTPException(
                    status_code=401,
                    detail="cvoice.ai key validation failed. Check the key and try again.",
                )
                
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
            logger.warning("ElevenLabs validation failed (%s).", type(e).__name__)
            raise HTTPException(
                status_code=401,
                detail="ElevenLabs key validation failed. Check the key and try again.",
            )

    if not payload.gemini_key:
        raise HTTPException(status_code=400, detail="Key required")
    clean_key = payload.gemini_key.strip()
    provider = detect_provider_from_key(clean_key, payload.provider)

    try:
        return _validate_provider_key(provider, clean_key, payload.base_url, payload.active_model)
    except HTTPException:
        raise
    except Exception as e:
        spec = provider_spec(provider)
        logger.warning("%s validation failed (%s).", spec.label, type(e).__name__)
        err_msg = str(e)
        if provider == "gemini" and ("API key expired" in err_msg or "400" in err_msg):
            detail = "API key expired. Please renew/regenerate your API key on Google AI Studio."
        elif isinstance(e, httpx.TimeoutException):
            detail = f"{spec.label} validation timed out. Please try again."
        elif isinstance(e, httpx.HTTPStatusError):
            detail = (
                f"{spec.label} rejected the validation request "
                f"(HTTP {e.response.status_code})."
            )
        else:
            detail = f"{spec.label} key validation failed. Check the provider settings and try again."
        raise HTTPException(status_code=401, detail=detail)


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
    provider = normalize_provider(payload.provider) if payload.provider else ""

    if payload.gemini_key:
        key = payload.gemini_key.strip()
        _save_pref(db, "GEMINI_API_KEY", key)
        provider = detect_provider_from_key(key, provider)
        _save_pref(db, "GEMINI_API_PROVIDER", provider)
    elif payload.provider is not None:
        _save_pref(db, "GEMINI_API_PROVIDER", provider)

    if payload.base_url is not None:
        _save_pref(db, "GEMINI_API_BASE_URL", payload.base_url.strip())

    if payload.active_model is not None:
        if not provider:
            provider_pref = db.query(UserPreferences).filter(UserPreferences.key == "GEMINI_API_PROVIDER").first()
            raw_provider = _decrypt_pref_value(provider_pref)
            provider = normalize_provider(raw_provider) if raw_provider else "gemini"
        provider = provider or "gemini"
        _save_pref(db, "GEMINI_ACTIVE_MODEL", _model_for_provider(provider, payload.active_model))

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
