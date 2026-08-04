from unittest.mock import AsyncMock

import pytest
from fastapi import BackgroundTasks, HTTPException

from backend.api.routes import settings
from backend.api.telegram_bot import telegram_bot_manager
from backend.database.connection import SessionLocal
from backend.database.crypto import crypto_manager
from backend.database.models import UserPreferences


_KEYS = (
    "TELEGRAM_BOT_ENABLED",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "TELEGRAM_PAIRING_CODE",
)


@pytest.fixture
def telegram_db():
    db = SessionLocal()
    db.query(UserPreferences).filter(UserPreferences.key.in_(_KEYS)).delete(
        synchronize_session=False
    )
    db.commit()
    try:
        yield db
    finally:
        db.query(UserPreferences).filter(UserPreferences.key.in_(_KEYS)).delete(
            synchronize_session=False
        )
        db.commit()
        db.close()


def _stored(db, key):
    return db.query(UserPreferences).filter(UserPreferences.key == key).first()


@pytest.mark.asyncio
async def test_save_enables_bot_and_awaits_async_restart(telegram_db, monkeypatch):
    restart = AsyncMock()
    monkeypatch.setattr(telegram_bot_manager, "restart", restart)
    tasks = BackgroundTasks()

    result = settings.save_telegram_settings(
        settings.TelegramSettingsPayload(
            enabled=True,
            bot_token="123456789:valid-looking-test-token",
        ),
        tasks,
        telegram_db,
    )
    await tasks()

    assert result == {"status": "success"}
    assert crypto_manager.decrypt(_stored(telegram_db, "TELEGRAM_BOT_ENABLED").value) == "true"
    assert crypto_manager.decrypt(_stored(telegram_db, "TELEGRAM_BOT_TOKEN").value) == "123456789:valid-looking-test-token"
    restart.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_reset_pairing_awaits_async_restart(telegram_db, monkeypatch):
    settings._save_pref(telegram_db, "TELEGRAM_CHAT_ID", "987654321")
    telegram_db.commit()
    restart = AsyncMock()
    monkeypatch.setattr(telegram_bot_manager, "restart", restart)
    tasks = BackgroundTasks()

    result = settings.reset_telegram_pairing(tasks, telegram_db)
    await tasks()

    assert result == {"status": "success"}
    assert _stored(telegram_db, "TELEGRAM_CHAT_ID") is None
    restart.assert_awaited_once_with()


def test_enable_rejects_missing_token_without_false_success(telegram_db):
    with pytest.raises(HTTPException) as exc_info:
        settings.save_telegram_settings(
            settings.TelegramSettingsPayload(enabled=True),
            BackgroundTasks(),
            telegram_db,
        )

    assert exc_info.value.status_code == 400
    assert "token is required" in exc_info.value.detail
    assert _stored(telegram_db, "TELEGRAM_BOT_ENABLED") is None


def test_enable_rejects_unreadable_saved_token(telegram_db):
    telegram_db.add(
        UserPreferences(key="TELEGRAM_BOT_TOKEN", value="corrupted-ciphertext")
    )
    telegram_db.commit()

    with pytest.raises(HTTPException) as exc_info:
        settings.save_telegram_settings(
            settings.TelegramSettingsPayload(enabled=True),
            BackgroundTasks(),
            telegram_db,
        )

    assert exc_info.value.status_code == 401
    assert "re-enter" in exc_info.value.detail
    assert _stored(telegram_db, "TELEGRAM_BOT_ENABLED") is None


def test_get_does_not_call_unreadable_ciphertext_configured(telegram_db):
    telegram_db.add(
        UserPreferences(key="TELEGRAM_BOT_ENABLED", value="corrupted-enabled")
    )
    telegram_db.add(
        UserPreferences(key="TELEGRAM_BOT_TOKEN", value="corrupted-ciphertext")
    )
    telegram_db.commit()

    result = settings.get_telegram_settings(telegram_db)

    assert result["enabled"] is False
    assert result["token_configured"] is False
    assert "enabled setting is unreadable" in result["configuration_error"]
    assert "re-enter" in result["configuration_error"]
