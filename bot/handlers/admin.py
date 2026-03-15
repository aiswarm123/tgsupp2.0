from __future__ import annotations

import logging
from typing import Callable, Optional

import aiosqlite
from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.config import settings
from bot.db import queries
from bot.keyboards.inline import admin_ticket_kb

logger = logging.getLogger(__name__)
router = Router()


# ── /register_group ───────────────────────────────────────────────────────────

@router.message(Command("register_group"))
async def cmd_register_group(message: Message, db: aiosqlite.Connection) -> None:
    if message.from_user.id not in settings.admin_ids:
        await message.reply("Unauthorized.")
        return
    chat = message.chat
    if chat.type not in ("supergroup", "group"):
        await message.reply("This command must be used in a forum supergroup.")
        return
    group_id, is_new = await queries.register_group(db, chat.id)
    if not is_new:
        await message.reply(f"This group is already registered (ID: {group_id}).")
        return
    await message.reply(f"✅ Group {chat.id} registered as a support group (ID: {group_id}).")


# ── /stats ────────────────────────────────────────────────────────────────────

@router.message(Command("stats"))
async def cmd_stats(message: Message, db: aiosqlite.Connection) -> None:
    stats = await queries.get_stats(db)
    avg_rt = stats["avg_response_time"]
    if avg_rt is None:
        avg_str = "N/A"
    elif avg_rt < 60:
        avg_str = f"{avg_rt:.0f}s"
    elif avg_rt < 3600:
        avg_str = f"{avg_rt / 60:.1f}m"
    else:
        avg_str = f"{avg_rt / 3600:.1f}h"

    await message.reply(
        "📊 <b>Support Stats</b>\n\n"
        f"Open tickets: {stats['open_count']}\n"
        f"Closed tickets: {stats['closed_count']}\n"
        f"Avg first response: {avg_str}\n"
        f"Active agents (24h): {stats['active_agents']}",
        parse_mode="HTML",
    )


# ── /toggle_ai ────────────────────────────────────────────────────────────────

@router.message(Command("toggle_ai"))
async def cmd_toggle_ai(
    message: Message, db: aiosqlite.Connection, t: Callable[[str], str]
) -> None:
    if message.from_user.id not in settings.admin_ids:
        await message.reply("Unauthorized.")
        return
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
    conv = await queries.get_conversation_by_id(db, conv_id)
    if conv is None:
        await callback.answer("Conversation not found.", show_alert=True)
        return

    # Issue #11: verify the conversation's user belongs to the group where
    # this callback originated — prevents cross-group close operations.
    origin_group = await queries.get_group_by_telegram_id(db, callback.message.chat.id)
    if origin_group is None:
        await callback.answer("Unrecognised group.", show_alert=True)
        return

    user = await queries.get_user_by_id(db, conv["user_id"])
    if user is None or user["group_id"] != origin_group["id"]:
        await callback.answer(
            "Permission denied: conversation belongs to a different group.",
            show_alert=True,
        )
        return

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
    # Issue #22: guard against channel posts and anonymous senders
    if not message.from_user:
        return

    if message.from_user.is_bot:
        return

    # Issue #14: only process messages from registered admin groups
    admin_group = await queries.get_group_by_telegram_id(db, message.chat.id)
    if admin_group is None:
        return

    # Issue #3: filter by both group_id and topic_id to prevent cross-group
    # misdelivery when the same topic_id appears in multiple forum groups.
    async with db.execute(
        "SELECT u.telegram_id, c.id AS conv_id FROM users u "
        "JOIN conversations c ON c.user_id = u.id "
        "WHERE u.group_id = ? AND u.topic_id = ? AND c.status != 'closed' "
        "ORDER BY c.id DESC LIMIT 1",
        (admin_group["id"], message.message_thread_id),
    ) as cur:
        row = await cur.fetchone()

    if row is None:
        return

    user_telegram_id, conv_id = row[0], row[1]

    # Issue #12: handle non-text messages (photos, voice, stickers, etc.)
    text = message.text or message.caption or ""
    if not text:
        logger.warning(
            "Agent sent non-text message (type=%s) in conv %s; forwarding media to user %s",
            message.content_type,
            conv_id,
            user_telegram_id,
        )
        try:
            await message.copy_to(chat_id=user_telegram_id)
        except Exception:
            logger.exception(
                "Failed to forward media message to user %s", user_telegram_id
            )
        await queries.save_message(db, conv_id, "agent", f"[{message.content_type}]")
        await queries.set_ai_enabled(db, conv_id, False)
        await queries.set_conversation_status(db, conv_id, "human")
        return

    await queries.save_message(db, conv_id, "agent", text, sender_id=message.from_user.id)
    await queries.set_ai_enabled(db, conv_id, False)
    await queries.set_conversation_status(db, conv_id, "human")

    try:
        await bot.send_message(chat_id=user_telegram_id, text=text)
    except Exception:
        logger.exception("Failed to deliver agent reply to user %s", user_telegram_id)
