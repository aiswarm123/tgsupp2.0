from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def talk_to_human_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Talk to human 🙋", callback_data="escalate")]
    ])


def admin_ticket_kb(conversation_id: int, ai_enabled: bool) -> InlineKeyboardMarkup:
    ai_label = "Disable AI 🤖" if ai_enabled else "Enable AI 🤖"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="Close ✅",
                callback_data=f"close:{conversation_id}",
            ),
            InlineKeyboardButton(
                text=ai_label,
                callback_data=f"toggle_ai:{conversation_id}",
            ),
        ]
    ])
