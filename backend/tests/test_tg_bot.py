import asyncio
from backend.api.telegram_bot import telegram_bot_manager

async def test_bot():
    print("Starting Telegram Bot Manager...")
    telegram_bot_manager.start()
    print(f"Bot enabled: {telegram_bot_manager.enabled}, Token present: {bool(telegram_bot_manager.bot_token)}, Paired chat: {telegram_bot_manager.chat_id}")
    print("Polling for 10 seconds...")
    await asyncio.sleep(10)
    print("Stopping Telegram Bot Manager...")
    await telegram_bot_manager.stop()
    print("Done!")

if __name__ == "__main__":
    asyncio.run(test_bot())
