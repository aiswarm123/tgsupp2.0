import logging
from datetime import datetime

import aiosqlite
from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.config import settings
from bot.db import queries
from bot.keyboards.inline import admin_controls_keyboard

logger = logging.getLogger(__name__)
router = Router()

_THRESHOLD_80 = 7_600
_THRESHOLD_95 = 9_025


# ---------------------------------------------------------------------------
# Capacity alerts
# ---------------------------------------------------------------------------

async def _check_and_alert_capacity(
    bot: Bot, group_telegram_id: int, topic_count: int
) -> None:
    """Send DM alerts to configured admins if topic count crosses a threshold."""
    if topic_count == _THRESHOLD_80:
        text = (
            f"⚠️ Admin group {group_telegram_id} has reached 80% capacity "
            f"({topic_count} / 9500 topics). Consider registering a new forum group soon."
        )
    elif topic_count == _THRESHOLD_95:
        text = (
            f"🚨 Admin group {group_telegram_id} has reached 95% capacity "
            f"({topic_count} / 9500 topics). Register a new forum supergroup immediately!"
        )
    else:
        return

    for admin_id in settings.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text)
        except Exception as exc:
            logger.warning("Failed to alert admin %s: %s", admin_id, exc)


# ---------------------------------------------------------------------------
# Agent reply detection
# ---------------------------------------------------------------------------

@router.message(
    F.chat.type == "supergroup",
    F.message_thread_id.is_not(None),
    F.from_user.is_not(None),
    F.from_user.is_bot.is_(False),
)
async def handle_agent_reply(message: Message, bot: Bot, db: aiosqlite.Connection) -> None:
    """Forward an agent's reply from the admin forum topic to the user."""
    # Resolve the user who owns this topic
    user = await queries.get_user_by_topic(db, message.chat.id, message.message_thread_id)
    if user is None:
        return  # Unknown topic — not one of ours

    conv = await queries.get_active_conversation(db, user["id"])
    if conv is None or conv["status"] == "closed":
        return

    text = message.text or message.caption
    if not text:
        return  # Ignore media-only messages for now

    try:
        await bot.send_message(user["telegram_id"], text)
    except Exception as exc:
        logger.error(
            "Failed to deliver agent message to user %s: %s",
            user["telegram_id"],
            exc,
        )
        return

    await queries.add_message(db, conv["id"], "agent", text, sender_id=message.from_user.id)

    # Disable AI auto-replies and mark conversation as human-handled
    if conv["ai_enabled"]:
        await queries.set_ai_enabled(db, conv["id"], False)
    if conv["status"] == "ai":
        await queries.set_conversation_status(db, conv["id"], "human")


# ---------------------------------------------------------------------------
# Inline callbacks
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("close_ticket:"))
async def handle_close_ticket(callback: CallbackQuery, db: aiosqlite.Connection) -> None:
    conv_id = int(callback.data.split(":", 1)[1])
    conv = await queries.get_conversation_by_id(db, conv_id)
    if conv is None:
        await callback.answer("Conversation not found.")
        return

    if conv["status"] == "closed":
        await callback.answer("Already closed.")
        return

    await queries.set_conversation_status(
        db,
        conv_id,
        "closed",
        closed_by=callback.from_user.id,
        closed_at=datetime.utcnow(),
    )

    keyboard = admin_controls_keyboard(conv_id, ai_enabled=bool(conv["ai_enabled"]), closed=True)
    await callback.message.edit_reply_markup(reply_markup=keyboard)
    await callback.answer("Ticket closed.")


@router.callback_query(F.data.startswith("toggle_ai:"))
async def handle_toggle_ai(callback: CallbackQuery, db: aiosqlite.Connection) -> None:
    conv_id = int(callback.data.split(":", 1)[1])
    conv = await queries.get_conversation_by_id(db, conv_id)
    if conv is None:
        await callback.answer("Conversation not found.")
        return

    new_ai_enabled = not bool(conv["ai_enabled"])
    await queries.set_ai_enabled(db, conv_id, new_ai_enabled)

    # If AI is re-enabled on a human-handled conversation, switch status back to 'ai'
    if new_ai_enabled and conv["status"] == "human":
        await queries.set_conversation_status(db, conv_id, "ai")

    closed = conv["status"] == "closed"
    keyboard = admin_controls_keyboard(conv_id, ai_enabled=new_ai_enabled, closed=closed)
    await callback.message.edit_reply_markup(reply_markup=keyboard)
    await callback.answer(f"AI {'enabled' if new_ai_enabled else 'disabled'}.")


@router.callback_query(F.data == "noop")
async def handle_noop(callback: CallbackQuery) -> None:
    await callback.answer()


# ---------------------------------------------------------------------------
# Admin commands
# ---------------------------------------------------------------------------

@router.message(Command("register_group"), F.chat.type == "supergroup")
async def handle_register_group(message: Message, bot: Bot, db: aiosqlite.Connection) -> None:
    """Register the current supergroup as an admin support group."""
    if not message.chat.is_forum:
        await message.reply(
            "This command must be used in a forum supergroup (Topics must be enabled)."
        )
        return

    # Only group administrators may register
    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in ("administrator", "creator"):
        await message.reply("Only group administrators can register a support group.")
        return

    group_id, is_new = await queries.register_admin_group(db, message.chat.id)
    if not is_new:
        await message.reply(
            f"This group is already registered (ID: {group_id})."
        )
        return

    await message.reply(
        f"✅ Group registered successfully (internal ID: {group_id}). "
        "New users will be routed to this group."
    )


@router.message(Command("stats"))
async def handle_stats(message: Message, db: aiosqlite.Connection) -> None:
    """Show ticket statistics."""
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


@router.message(Command("toggle_ai"), F.chat.type.in_({"supergroup", "group", "private"}))
async def handle_toggle_ai_command(message: Message, db: aiosqlite.Connection) -> None:
    """Manually toggle AI for a user's conversation: /toggle_ai <user_id>"""
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].lstrip("-").isdigit():
        await message.reply("Usage: /toggle_ai <user_id>")
        return

    telegram_id = int(parts[1])
    user = await queries.get_user_by_telegram_id(db, telegram_id)
    if user is None:
        await message.reply(f"No user found with Telegram ID {telegram_id}.")
        return

    conv = await queries.get_active_conversation(db, user["id"])
    if conv is None:
        await message.reply("No active conversation found for this user.")
        return

    new_ai_enabled = not bool(conv["ai_enabled"])
    await queries.set_ai_enabled(db, conv["id"], new_ai_enabled)
    state = "enabled" if new_ai_enabled else "disabled"
    await message.reply(f"AI {state} for user {telegram_id} (conversation #{conv['id']}).")
