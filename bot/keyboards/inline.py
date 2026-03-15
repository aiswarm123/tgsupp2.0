from typing import Callable, Optional

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def talk_to_human_kb(t: Optional[Callable[[str], str]] = None) -> InlineKeyboardMarkup:
    label = t("talk_to_human") if t is not None else "Talk to human 🙋"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data="escalate")]
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
