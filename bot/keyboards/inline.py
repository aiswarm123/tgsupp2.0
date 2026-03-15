from typing import Callable, Optional

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


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


def faq_admin_list_kb(items: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item in items:
        fid = item["id"]
        builder.row(
            InlineKeyboardButton(text=item["question"], callback_data=f"faq_noop:{fid}"),
        )
        builder.row(
            InlineKeyboardButton(text="Edit", callback_data=f"faq_edit:{fid}"),
            InlineKeyboardButton(text="Delete", callback_data=f"faq_del:{fid}"),
        )
    builder.row(InlineKeyboardButton(text="+ Add new", callback_data="faq_add"))
    return builder.as_markup()


def faq_confirm_delete_kb(faq_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Yes", callback_data=f"faq_del_yes:{faq_id}"),
            InlineKeyboardButton(text="No", callback_data="faq_del_no"),
        ]
    ])


def faq_user_kb(items: list[dict]) -> InlineKeyboardMarkup:
    """Inline keyboard with one button per FAQ item."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=item["question"], callback_data=f"faq:{item['id']}")]
        for item in items
    ])


def faq_back_kb(t: Optional[Callable[[str], str]] = None) -> InlineKeyboardMarkup:
    """Single back button to return to FAQ list."""
    label = t("back") if t is not None else "\u2190 Back"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data="faq:back")]
    ])
