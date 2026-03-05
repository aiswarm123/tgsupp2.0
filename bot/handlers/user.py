from __future__ import annotations

import logging
from typing import Callable, Optional

import aiosqlite
from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from bot.ai.client import send_message
from bot.config import settings
from bot.db import queries
from bot.keyboards.inline import admin_ticket_kb, talk_to_human_kb

logger = logging.getLogger(__name__)
router = Router()

_WARN_80 = 7_600
_WARN_95 = 9_025


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _get_group_tg_id(db: aiosqlite.Connection, group_id: int) -> Optional[int]:
    async with db.execute(
        "SELECT telegram_group_id FROM admin_groups WHERE id = ?", (group_id,)
    ) as cur:
        row = await cur.fetchone()
    return row[0] if row else None


async def _maybe_warn_capacity(bot: Bot, db: aiosqlite.Connection, count: int) -> None:
    if count == _WARN_80:
        text = f"⚠️ Admin group is at 80% capacity ({count}/9500 topics)."
    elif count == _WARN_95:
        text = f"🚨 Admin group is at 95% capacity ({count}/9500 topics). Please register a new group soon."
    else:
        return

    group_ids = await queries.get_all_active_group_ids(db)
    for gid in group_ids:
        try:
            await bot.send_message(gid, text)
        except Exception:
            logger.exception("Failed to send capacity warning to group %s", gid)


async def _ensure_user_and_conv(
    db: aiosqlite.Connection,
    bot: Bot,
    tg_user,
    lang: str,
) -> tuple[Optional[dict], Optional[dict]]:
    """Return (user, conversation), creating both on first contact."""
    user = await queries.get_user(db, tg_user.id)

    if user is None:
        group = await queries.get_active_group(db)
        if group is None:
            return None, None

        name = (tg_user.full_name or tg_user.username or str(tg_user.id))[:128]
        forum_topic = await bot.create_forum_topic(
            chat_id=group["telegram_group_id"],
            name=name,
        )
        topic_id = forum_topic.message_thread_id

        user_id = await queries.create_user(
            db,
            telegram_id=tg_user.id,
            language=lang,
            group_id=group["id"],
            topic_id=topic_id,
        )
        user = {
            "id": user_id,
            "telegram_id": tg_user.id,
            "language": lang,
            "group_id": group["id"],
            "topic_id": topic_id,
        }

        count = await queries.increment_topic_count(db, group["id"])
        await _maybe_warn_capacity(bot, db, count)

    conv = await queries.get_open_conversation(db, user["id"])
    if conv is None:
        conv_id = await queries.create_conversation(db, user["id"])
        conv = {"id": conv_id, "status": "ai", "ai_enabled": True}

    return user, conv


# ── Handlers ───────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def handle_start(
    message: Message,
    bot: Bot,
    db: aiosqlite.Connection,
    t: Callable[[str], str],
    lang: str,
) -> None:
    await _process_user_message(message, bot, db, t, lang)


@router.message(F.chat.type == "private")
async def handle_private_message(
    message: Message,
    bot: Bot,
    db: aiosqlite.Connection,
    t: Callable[[str], str],
    lang: str,
) -> None:
    await _process_user_message(message, bot, db, t, lang)


async def _process_user_message(
    message: Message,
    bot: Bot,
    db: aiosqlite.Connection,
    t: Callable[[str], str],
    lang: str,
) -> None:
    tg_user = message.from_user
    if tg_user is None:
        return

    user, conv = await _ensure_user_and_conv(db, bot, tg_user, lang)
    if user is None:
        await message.answer(t("no_group"))
        return

    text = message.text or message.caption or ""
    await queries.save_message(db, conv["id"], "user", text)

    tg_group_id = await _get_group_tg_id(db, user["group_id"])
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

    if not conv["ai_enabled"]:
        return

    history = await queries.get_conversation_history(db, conv["id"])
    try:
        ai_text = await send_message(history, settings.ai_system_prompt)
    except Exception:
        logger.exception("AI call failed for conversation %s", conv["id"])
        await message.answer(t("ai_unavailable"), reply_markup=talk_to_human_kb())
        return

    await queries.save_message(db, conv["id"], "ai", ai_text)
    await message.answer(ai_text, reply_markup=talk_to_human_kb())

    if tg_group_id:
        try:
            await bot.send_message(
                chat_id=tg_group_id,
                text=f"🤖 {ai_text}",
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

    await queries.set_ai_enabled(db, conv["id"], False)
    await queries.set_conversation_status(db, conv["id"], "human")

    await callback.answer(t("escalated"))
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    tg_group_id = await _get_group_tg_id(db, user["group_id"])
    if tg_group_id is None:
        return

    user_mention = f'<a href="tg://user?id={tg_user.id}">{tg_user.full_name}</a>'
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
