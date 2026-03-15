import asyncio
import logging
import os

import aiosqlite
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from bot.config import settings
from bot.db.models import init_db
from bot.handlers import admin, user

logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
logger = logging.getLogger(__name__)


async def main() -> None:
    os.makedirs(os.path.dirname(settings.DB_PATH), exist_ok=True)
    await init_db(settings.DB_PATH)

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    dp = Dispatcher()

    async with aiosqlite.connect(settings.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        dp.workflow_data.update(db=db)

        dp.include_router(admin.router)
        dp.include_router(user.router)

        logger.info("Starting bot...")
        await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
