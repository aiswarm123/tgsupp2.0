from typing import Callable, Optional

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def admin_controls_keyboard(
    conv_id: int, ai_enabled: bool, closed: bool = False
) -> InlineKeyboardMarkup:
    """Keyboard shown in admin forum topic for each conversation."""
    builder = InlineKeyboardBuilder()
    if not closed:
        builder.row(
            InlineKeyboardButton(
                text="Close ✅",
                callback_data=f"close_ticket:{conv_id}",
            ),
            InlineKeyboardButton(
                text="AI: ON 🤖" if ai_enabled else "AI: OFF 🤖",
                callback_data=f"toggle_ai:{conv_id}",
            ),
        )
    else:
        # Conversation is closed — only allow toggling AI (e.g. to re-enable before reopening)
        builder.row(
            InlineKeyboardButton(
                text="Closed ✅",
                callback_data="noop",
            ),
            InlineKeyboardButton(
                text="AI: ON 🤖" if ai_enabled else "AI: OFF 🤖",
                callback_data=f"toggle_ai:{conv_id}",
            ),
        )
    return builder.as_markup()


def user_escalation_keyboard(
    conv_id: int, t: Optional[Callable[[str], str]] = None
) -> InlineKeyboardMarkup:
    """Button shown to the user under AI replies."""
    label = t("talk_to_human") if t is not None else "Talk to human 🙋"
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=label,
            callback_data=f"human_request:{conv_id}",
        )
    )
    return builder.as_markup()
