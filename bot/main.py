from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import load_settings
from bot.db import Database
from bot.handlers import admin, chat, menu, reminders, schedule, start, tasks
from bot.llm import OllamaClient
from bot.middlewares import DbUserMiddleware
from bot.reminders import ReminderService
from bot.stickers import StickerService

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("bot")


async def main() -> None:
    settings = load_settings()
    db = Database(settings.db_path)
    await db.connect()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    stickers = StickerService(settings.sticker_set)
    await stickers.load(bot)

    llm = OllamaClient(
        base_url=settings.ollama_url,
        model=settings.ollama_model,
        timeout=settings.ollama_timeout,
    )
    await llm.open()

    dp = Dispatcher(storage=MemoryStorage())
    dp["settings"] = settings
    dp["stickers"] = stickers
    dp["db"] = db
    dp["llm"] = llm

    user_mw = DbUserMiddleware(db)
    dp.message.middleware(user_mw)
    dp.callback_query.middleware(user_mw)

    @dp.update.outer_middleware()
    async def inject_services(handler, event, data):
        data["settings"] = settings
        data["stickers"] = stickers
        data["db"] = db
        data["llm"] = llm
        return await handler(event, data)

    dp.include_router(start.router)
    dp.include_router(menu.router)
    dp.include_router(tasks.router)
    dp.include_router(schedule.router)
    dp.include_router(reminders.router)
    dp.include_router(admin.router)
    dp.include_router(chat.router)

    reminder_service = ReminderService(bot, db, settings, stickers)
    reminder_service.start()

    try:
        logger.info("Kuromi bot starting…")
        await dp.start_polling(bot)
    finally:
        reminder_service.shutdown()
        await llm.close()
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
