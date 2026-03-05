from __future__ import annotations

import logging
from typing import Callable, Optional

import aiosqlite
from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.db import queries
from bot.keyboards.inline import admin_ticket_kb

logger = logging.getLogger(__name__)
router = Router()


# ── /register_group ───────────────────────────────────────────────────────────

@router.message(Command("register_group"))
async def cmd_register_group(message: Message, db: aiosqlite.Connection) -> None:
    chat = message.chat
    if chat.type not in ("supergroup", "group"):
        await message.reply("This command must be used in a forum supergroup.")
        return
    await queries.register_group(db, chat.id)
    await message.reply(f"Group {chat.id} registered as a support group.")


# ── /toggle_ai ────────────────────────────────────────────────────────────────

@router.message(Command("toggle_ai"))
async def cmd_toggle_ai(
    message: Message, db: aiosqlite.Connection, t: Callable[[str], str]
) -> None:
    parts = message.text.split()
    if len(parts) < 2:
        await message.reply("Usage: /toggle_ai <user_id>")
        return
    try:
        telegram_id = int(parts[1])
    except ValueError:
        await message.reply("Invalid user_id.")
        return

    user = await queries.get_user(db, telegram_id)
    if user is None:
        await message.reply("User not found.")
        return

    conv = await queries.get_open_conversation(db, user["id"])
    if conv is None:
        await message.reply("No open conversation for this user.")
        return

    new_state = not conv["ai_enabled"]
    await queries.set_ai_enabled(db, conv["id"], new_state)
    label = t("ai_toggled_on") if new_state else t("ai_toggled_off")
    await message.reply(label)


# ── Close ticket callback ─────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("close:"))
async def handle_close(
    callback: CallbackQuery,
    db: aiosqlite.Connection,
    t: Callable[[str], str],
) -> None:
    conv_id = int(callback.data.split(":")[1])
    closed_by = callback.from_user.id
    await queries.set_conversation_status(db, conv_id, "closed", closed_by=closed_by)
    await callback.answer(t("ticket_closed_admin"))
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


# ── Toggle AI callback ────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("toggle_ai:"))
async def handle_toggle_ai(
    callback: CallbackQuery,
    db: aiosqlite.Connection,
    t: Callable[[str], str],
) -> None:
    conv_id = int(callback.data.split(":")[1])
    conv = await queries.get_conversation_by_id(db, conv_id)
    if conv is None:
        await callback.answer("Conversation not found.", show_alert=True)
        return

    new_state = not conv["ai_enabled"]
    await queries.set_ai_enabled(db, conv_id, new_state)
    label = t("ai_toggled_on") if new_state else t("ai_toggled_off")
    await callback.answer(label)
    try:
        await callback.message.edit_reply_markup(
            reply_markup=admin_ticket_kb(conv_id, ai_enabled=new_state)
        )
    except Exception:
        pass


# ── Agent replies in admin topic → forward to user ───────────────────────────

@router.message(F.chat.type.in_({"supergroup", "group"}) & F.message_thread_id.is_not(None))
async def handle_admin_reply(
    message: Message,
    bot: Bot,
    db: aiosqlite.Connection,
) -> None:
    """Forward agent replies from admin topic to the corresponding user."""
    if message.from_user and message.from_user.is_bot:
        return

    async with db.execute(
        "SELECT u.telegram_id, c.id AS conv_id FROM users u "
        "JOIN conversations c ON c.user_id = u.id "
        "WHERE u.topic_id = ? AND c.status != 'closed' "
        "ORDER BY c.id DESC LIMIT 1",
        (message.message_thread_id,),
    ) as cur:
        row = await cur.fetchone()

    if row is None:
        return

    user_telegram_id, conv_id = row[0], row[1]
    text = message.text or message.caption or ""
    if not text:
        return

    await queries.save_message(db, conv_id, "agent", text)
    await queries.set_ai_enabled(db, conv_id, False)
    await queries.set_conversation_status(db, conv_id, "human")

    try:
        await bot.send_message(chat_id=user_telegram_id, text=text)
    except Exception:
        logger.exception("Failed to deliver agent reply to user %s", user_telegram_id)
