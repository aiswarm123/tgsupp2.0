import asyncio
import logging
import os
from typing import Any, Awaitable, Callable

import aiosqlite
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import TelegramObject

from bot.config import settings
from bot.db.models import init_db
from bot.handlers import admin, user
from bot.middlewares.i18n import I18nMiddleware

logging.basicConfig(level=logging.INFO)


class _DbMiddleware:
    """Opens an aiosqlite connection per update and injects it as ``db``."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            data["db"] = db
            return await handler(event, data)


async def main() -> None:
    os.makedirs(os.path.dirname(settings.db_path) or ".", exist_ok=True)
    await init_db(settings.db_path)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    db_mw = _DbMiddleware(settings.db_path)
    dp.message.middleware(db_mw)
    dp.callback_query.middleware(db_mw)

    dp.message.middleware(I18nMiddleware())
    dp.callback_query.middleware(I18nMiddleware())

    dp.include_router(user.router)
    dp.include_router(admin.router)

    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    asyncio.run(main())
