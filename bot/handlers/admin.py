from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.config import settings

router = Router()


@router.message(Command("register_group"))
async def register_group(message: Message) -> None:
    if message.from_user.id not in settings.admin_ids:
        await message.reply("Unauthorized.")
        return

    # TODO: implement group registration logic
    await message.reply("Group registered.")


@router.message(Command("toggle_ai"))
async def toggle_ai(message: Message) -> None:
    if message.from_user.id not in settings.admin_ids:
        await message.reply("Unauthorized.")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].isdigit():
        await message.reply("Usage: /toggle_ai <user_id>")
        return

    user_id = int(args[1])
    # TODO: implement AI toggle logic
    await message.reply(f"AI toggled for user {user_id}.")
