from __future__ import annotations

import html
import logging
from typing import Callable, Optional

import aiosqlite
from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from bot.ai.client import send_message
from bot.config import settings
from bot.db import queries
from bot.keyboards.inline import (
    admin_ticket_kb,
    faq_back_kb,
    faq_user_kb,
    talk_to_human_kb,
)

logger = logging.getLogger(__name__)
router = Router()

_WARN_80 = 7_600
_WARN_95 = 9_025


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _maybe_warn_capacity(bot: Bot, db: aiosqlite.Connection, count: int) -> None:
    if _WARN_80 <= count < _WARN_95:
        text = f"\u26a0\ufe0f Admin group is at 80% capacity ({count}/9500 topics)."
    elif count >= _WARN_95:
        text = (
            f"\ud83d\udea8 Admin group is at 95% capacity ({count}/9500 topics). "
            "Please register a new group soon."
        )
    else:
        return

    group_ids = await queries.get_all_active_group_ids(db)
    for gid in group_ids:
        try:
            await bot.send_message(gid, text)
        except Exception:
            logger.exception("Failed to send capacity warning to group %s", gid)


def _topic_name(tg_user) -> str:
    """Build admin-topic name: 'Full Name (@username, ID: 123)'."""
    full_name = tg_user.full_name or str(tg_user.id)
    if tg_user.username:
        name = f"{full_name} (@{tg_user.username}, ID: {tg_user.id})"
    else:
        name = f"{full_name} (ID: {tg_user.id})"
    return name[:128]


async def _ensure_user(
    db: aiosqlite.Connection, tg_user, lang: str
) -> Optional[dict]:
    """Get or create user record (without topic — that happens on first message)."""
    user = await queries.get_user(db, tg_user.id)
    if user is not None:
        return user

    try:
        user_id = await queries.create_user(
            db, telegram_id=tg_user.id, language=lang,
        )
    except aiosqlite.IntegrityError:
        user = await queries.get_user(db, tg_user.id)
        return user

    return {
        "id": user_id,
        "telegram_id": tg_user.id,
        "language": lang,
        "group_id": None,
        "topic_id": None,
    }


async def _ensure_topic(
    db: aiosqlite.Connection, bot: Bot, user: dict, tg_user
) -> Optional[dict]:
    """Create admin topic for user if they don't have one yet. Returns updated user or None."""
    if user["topic_id"] is not None:
        return user

    group = await queries.get_active_group(db)
    if group is None:
        return None

    try:
        forum_topic = await bot.create_forum_topic(
            chat_id=group["telegram_group_id"],
            name=_topic_name(tg_user),
        )
    except TelegramAPIError:
        logger.exception(
            "Failed to create forum topic in group %s for user %s",
            group["telegram_group_id"],
            tg_user.id,
        )
        return None

    topic_id = forum_topic.message_thread_id
    await queries.update_user_topic(db, tg_user.id, group["id"], topic_id)
    count = await queries.increment_topic_count(db, group["id"])
    await _maybe_warn_capacity(bot, db, count)

    user = dict(user)
    user["group_id"] = group["id"]
    user["topic_id"] = topic_id
    return user


# ── /start handler ─────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def handle_start(
    message: Message,
    bot: Bot,
    db: aiosqlite.Connection,
    t: Callable[[str], str],
    lang: str,
) -> None:
    tg_user = message.from_user
    if tg_user is None:
        return

    await _ensure_user(db, tg_user, lang)

    faq_items = await queries.get_faq_items(db)
    if faq_items:
        await message.answer(t("welcome"), reply_markup=faq_user_kb(faq_items))
    else:
        await message.answer(t("welcome"))


# ── FAQ callbacks ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "faq:back")
async def handle_faq_back(
    callback: CallbackQuery,
    db: aiosqlite.Connection,
    t: Callable[[str], str],
) -> None:
    faq_items = await queries.get_faq_items(db)
    if faq_items:
        await callback.message.edit_text(t("welcome"), reply_markup=faq_user_kb(faq_items))
    else:
        await callback.message.edit_text(t("welcome"))
    await callback.answer()


@router.callback_query(F.data.startswith("faq:"))
async def handle_faq_item(
    callback: CallbackQuery,
    db: aiosqlite.Connection,
    bot: Bot,
) -> None:
    faq_id_str = callback.data.split(":", 1)[1]
    try:
        faq_id = int(faq_id_str)
    except ValueError:
        await callback.answer()
        return

    item = await queries.get_faq_item(db, faq_id)
    if item is None:
        await callback.answer()
        return

    if item["media_file_id"]:
        # Send photo with answer as caption, then back button as separate message
        await callback.message.edit_text(item["answer"], reply_markup=faq_back_kb())
        try:
            await bot.send_photo(
                chat_id=callback.message.chat.id,
                photo=item["media_file_id"],
            )
        except Exception:
            logger.exception("Failed to send FAQ media for item %s", faq_id)
    else:
        await callback.message.edit_text(item["answer"], reply_markup=faq_back_kb())

    await callback.answer()


# ── Private messages (escalation + normal flow) ────────────────────────────────

@router.message(F.chat.type == "private")
async def handle_private_message(
    message: Message,
    bot: Bot,
    db: aiosqlite.Connection,
    t: Callable[[str], str],
    lang: str,
) -> None:
    tg_user = message.from_user
    if tg_user is None:
        return

    user = await _ensure_user(db, tg_user, lang)
    if user is None:
        await message.answer(t("error_generic"))
        return

    # Ensure topic exists (deferred creation on first free-text message)
    first_escalation = user["topic_id"] is None
    user = await _ensure_topic(db, bot, user, tg_user)
    if user is None:
        await message.answer(t("no_group"))
        return

    # Get or create conversation
    conv = await queries.get_open_conversation(db, user["id"])
    if conv is None:
        conv_id = await queries.create_conversation(db, user["id"])
        conv = {"id": conv_id, "status": "ai", "ai_enabled": True}

    text = message.text or message.caption or f"[{message.content_type}]"
    await queries.save_message(db, conv["id"], "user", text)

    # Forward message to admin topic
    tg_group_id = await queries.get_group_tg_id(db, user["group_id"])
    if tg_group_id:
        try:
            await bot.forward_message(
                chat_id=tg_group_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
                message_thread_id=user["topic_id"],
            )
        except Exception:
            logger.exception("Failed to forward message to admin topic for user %s", tg_user.id)

    # First escalation notification
    if first_escalation:
        await message.answer(t("escalated_to_support"))

    # AI auto-reply
    if not settings.ai_available or not conv["ai_enabled"]:
        return

    history = await queries.get_conversation_history(db, conv["id"])
    try:
        ai_text = await send_message(history, settings.ai_system_prompt)
    except Exception:
        logger.exception("AI call failed for conversation %s", conv["id"])
        await message.answer(t("ai_unavailable"), reply_markup=talk_to_human_kb())
        return

    if ai_text is None:
        return

    await queries.save_message(db, conv["id"], "ai", ai_text)
    await message.answer(ai_text, reply_markup=talk_to_human_kb())

    if tg_group_id:
        try:
            await bot.send_message(
                chat_id=tg_group_id,
                text=f"\ud83e\udd16 {html.escape(ai_text)}",
                message_thread_id=user["topic_id"],
                parse_mode="HTML",
                reply_markup=admin_ticket_kb(conv["id"], ai_enabled=True),
            )
        except Exception:
            logger.exception("Failed to echo AI reply to admin topic for user %s", tg_user.id)


# ── Escalation callback ────────────────────────────────────────────────────────

@router.callback_query(F.data == "escalate")
async def handle_escalate(
    callback: CallbackQuery,
    bot: Bot,
    db: aiosqlite.Connection,
    t: Callable[[str], str],
) -> None:
    tg_user = callback.from_user
    user = await queries.get_user(db, tg_user.id)
    if user is None:
        await callback.answer(t("error_generic"), show_alert=True)
        return

    conv = await queries.get_open_conversation(db, user["id"])
    if conv is None or not conv["ai_enabled"]:
        await callback.answer(t("already_escalated"), show_alert=True)
        return

    await queries.escalate_to_human(db, conv["id"])

    await callback.answer(t("escalated"))
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    tg_group_id = await queries.get_group_tg_id(db, user["group_id"])
    if tg_group_id is None:
        return

    user_mention = f'<a href="tg://user?id={tg_user.id}">{html.escape(tg_user.full_name or str(tg_user.id))}</a>'
    priority_text = t("priority_flag").format(user_mention=user_mention)
    try:
        await bot.send_message(
            chat_id=tg_group_id,
            text=priority_text,
            message_thread_id=user["topic_id"],
            parse_mode="HTML",
            reply_markup=admin_ticket_kb(conv["id"], ai_enabled=False),
        )
    except Exception:
        logger.exception("Failed to send priority flag for user %s", tg_user.id)
