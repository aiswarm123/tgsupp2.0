import json
import logging
from pathlib import Path
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

logger = logging.getLogger(__name__)

LOCALES_DIR = Path(__file__).parent.parent / "locales"
SUPPORTED_LANGS = {"en", "ru", "ua"}
DEFAULT_LANG = "en"

# Language code prefixes from Telegram → internal lang
_LANG_MAP: dict[str, str] = {
    "ru": "ru",
    "uk": "ua",  # Ukrainian locale code in Telegram
    "en": "en",
}

_locale_cache: dict[str, dict[str, str]] = {}


def _load_locale(lang: str) -> dict[str, str]:
    if lang not in _locale_cache:
        path = LOCALES_DIR / f"{lang}.json"
        with path.open(encoding="utf-8") as f:
            _locale_cache[lang] = json.load(f)
    return _locale_cache[lang]


def _detect_lang(language_code: str | None) -> str:
    if not language_code:
        return DEFAULT_LANG
    prefix = language_code.split("-")[0].lower()
    return _LANG_MAP.get(prefix, DEFAULT_LANG)


def make_translator(lang: str) -> Callable[[str], str]:
    locale = _load_locale(lang)
    fallback = _load_locale(DEFAULT_LANG)

    def t(key: str) -> str:
        return locale.get(key) or fallback.get(key, key)

    return t


class I18nMiddleware(BaseMiddleware):
    """
    Detects or loads user language and injects a ``t()`` translator into handler data.

    On first contact the language is detected from ``message.from_user.language_code``
    and stored in the DB.  Subsequent messages use the stored value.

    Handler signature example::

        async def handler(message: Message, t: Callable[[str], str]):
            await message.answer(t("welcome"))
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        lang = await self._resolve_lang(event, data)
        data["t"] = make_translator(lang)
        data["lang"] = lang
        return await handler(event, data)

    async def _resolve_lang(self, event: TelegramObject, data: dict[str, Any]) -> str:
        user = getattr(event, "from_user", None)
        if user is None:
            return DEFAULT_LANG

        db = data.get("db")
        if db is not None:
            try:
                lang = await self._get_stored_lang(db, user.id)
                if lang:
                    return lang
            except Exception:
                logger.exception("i18n: failed to read language from DB for user %s", user.id)

        detected = _detect_lang(getattr(user, "language_code", None))

        if db is not None:
            try:
                await self._store_lang(db, user.id, detected)
            except Exception:
                logger.exception("i18n: failed to store language for user %s", user.id)

        return detected

    @staticmethod
    async def _get_stored_lang(db: Any, telegram_id: int) -> str | None:
        """Return stored language for ``telegram_id``, or None if not found."""
        # Fix #1: aiosqlite has no db.fetchone(); use cursor.fetchone() instead.
        async with db.execute(
            "SELECT language FROM users WHERE telegram_id = ?",
            (telegram_id,),
        ) as cur:
            row = await cur.fetchone()
        if row and row[0] in SUPPORTED_LANGS:
            return row[0]
        return None

    @staticmethod
    async def _store_lang(db: Any, telegram_id: int, lang: str) -> None:
        """Persist detected language for returning users only."""
        # UPDATE is a no-op if the user row doesn't exist yet (first contact);
        # create_user() in the handler owns new-user inserts.
        cur = await db.execute(
            "UPDATE users SET language = ? WHERE telegram_id = ?",
            (lang, telegram_id),
        )
        if cur.rowcount > 0:
            await db.commit()
