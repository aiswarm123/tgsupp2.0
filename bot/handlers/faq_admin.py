from __future__ import annotations

import html

import aiosqlite
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.config import settings
from bot.db import queries
from bot.handlers.admin import IsAdmin
from bot.keyboards.inline import faq_admin_list_kb, faq_confirm_delete_kb

router = Router()
_is_admin = IsAdmin()


class AddFAQ(StatesGroup):
    waiting_question = State()
    waiting_answer = State()


class EditFAQ(StatesGroup):
    waiting_question = State()
    waiting_answer = State()


# ── helpers ──────────────────────────────────────────────────────────────────

async def _send_faq_list(message: Message, db: aiosqlite.Connection) -> None:
    items = await queries.get_all_faq(db)
    if not items:
        await message.answer("No FAQ items yet.", reply_markup=faq_admin_list_kb([]))
        return
    text_parts = ["<b>FAQ items:</b>\n"]
    for i, item in enumerate(items, 1):
        text_parts.append(f"{i}. <b>{html.escape(item['question'])}</b>")
    await message.answer("\n".join(text_parts), reply_markup=faq_admin_list_kb(items))


# ── /faq command ─────────────────────────────────────────────────────────────

@router.message(Command("faq"), _is_admin, F.chat.type == "private")
async def cmd_faq(message: Message, db: aiosqlite.Connection, state: FSMContext) -> None:
    await state.clear()
    await _send_faq_list(message, db)


# ── Add flow ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "faq_add", _is_admin)
async def faq_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await callback.message.answer("Send the FAQ question (this will be the button label):")
    await state.set_state(AddFAQ.waiting_question)


@router.message(AddFAQ.waiting_question, F.text)
async def faq_add_question(message: Message, state: FSMContext) -> None:
    await state.update_data(question=message.text)
    await message.answer("Now send the answer (supports text, photos with caption, HTML formatting):")
    await state.set_state(AddFAQ.waiting_answer)


@router.message(AddFAQ.waiting_answer, F.photo)
async def faq_add_answer_photo(message: Message, state: FSMContext, db: aiosqlite.Connection) -> None:
    data = await state.get_data()
    answer_text = message.caption or ""
    media_file_id = message.photo[-1].file_id
    await queries.create_faq(db, data["question"], answer_text, media_file_id=media_file_id)
    await state.clear()
    await message.answer("FAQ item added!")
    await _send_faq_list(message, db)


@router.message(AddFAQ.waiting_answer, F.text)
async def faq_add_answer_text(message: Message, state: FSMContext, db: aiosqlite.Connection) -> None:
    data = await state.get_data()
    await queries.create_faq(db, data["question"], message.text)
    await state.clear()
    await message.answer("FAQ item added!")
    await _send_faq_list(message, db)


# ── Edit flow ────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("faq_edit:"), _is_admin)
async def faq_edit_start(callback: CallbackQuery, state: FSMContext, db: aiosqlite.Connection) -> None:
    faq_id = int(callback.data.split(":")[1])
    item = await queries.get_faq_by_id(db, faq_id)
    if item is None:
        await callback.answer("FAQ item not found.", show_alert=True)
        return
    await callback.answer()
    preview = f"<b>Question:</b> {html.escape(item['question'])}\n<b>Answer:</b> {html.escape(item['answer'])}"
    if item["media_file_id"]:
        preview += "\n(has attached photo)"
    await callback.message.answer(preview)
    await callback.message.answer('Send new question text (or /skip to keep current):')
    await state.set_state(EditFAQ.waiting_question)
    await state.update_data(faq_id=faq_id)


@router.message(EditFAQ.waiting_question, F.text)
async def faq_edit_question(message: Message, state: FSMContext) -> None:
    if message.text != "/skip":
        await state.update_data(new_question=message.text)
    await message.answer("Send new answer (or /skip to keep current):")
    await state.set_state(EditFAQ.waiting_answer)


@router.message(EditFAQ.waiting_answer, F.photo)
async def faq_edit_answer_photo(message: Message, state: FSMContext, db: aiosqlite.Connection) -> None:
    data = await state.get_data()
    faq_id = data["faq_id"]
    await queries.update_faq(
        db,
        faq_id,
        question=data.get("new_question"),
        answer=message.caption or "",
        media_file_id=message.photo[-1].file_id,
    )
    await state.clear()
    await message.answer("FAQ item updated!")
    await _send_faq_list(message, db)


@router.message(EditFAQ.waiting_answer, F.text)
async def faq_edit_answer_text(message: Message, state: FSMContext, db: aiosqlite.Connection) -> None:
    data = await state.get_data()
    faq_id = data["faq_id"]
    kwargs: dict = {}
    if "new_question" in data:
        kwargs["question"] = data["new_question"]
    if message.text != "/skip":
        kwargs["answer"] = message.text
    if kwargs:
        await queries.update_faq(db, faq_id, **kwargs)
    await state.clear()
    await message.answer("FAQ item updated!")
    await _send_faq_list(message, db)


# ── Delete flow ──────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("faq_del:"), _is_admin)
async def faq_delete_confirm(callback: CallbackQuery, db: aiosqlite.Connection) -> None:
    faq_id = int(callback.data.split(":")[1])
    item = await queries.get_faq_by_id(db, faq_id)
    if item is None:
        await callback.answer("FAQ item not found.", show_alert=True)
        return
    await callback.answer()
    await callback.message.answer(
        f"Delete <b>{html.escape(item['question'])}</b>? Are you sure?",
        reply_markup=faq_confirm_delete_kb(faq_id),
    )


@router.callback_query(F.data.startswith("faq_del_yes:"), _is_admin)
async def faq_delete_yes(callback: CallbackQuery, db: aiosqlite.Connection) -> None:
    faq_id = int(callback.data.split(":")[1])
    await queries.delete_faq(db, faq_id)
    await callback.answer("Deleted.")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await _send_faq_list(callback.message, db)


@router.callback_query(F.data == "faq_del_no")
async def faq_delete_no(callback: CallbackQuery) -> None:
    await callback.answer("Cancelled.")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


# ── No-op for question label buttons ────────────────────────────────────────

@router.callback_query(F.data.startswith("faq_noop:"))
async def faq_noop(callback: CallbackQuery) -> None:
    await callback.answer()
