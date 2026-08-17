from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot import texts
from bot.db import User
from bot.keyboards import main_menu
from bot.stickers import StickerService

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    db_user: User,
    stickers: StickerService,
    state: FSMContext,
) -> None:
    await state.clear()
    await stickers.send_mood(message.bot, message.chat.id, "start")
    await message.answer(
        texts.start_message(
            db_user.full_name or "",
            db_user.telegram_id,
            is_admin=db_user.is_admin,
        ),
        reply_markup=main_menu(db_user),
    )


@router.message(Command("help"))
async def cmd_help(message: Message, db_user: User) -> None:
    await message.answer(texts.help_message(), reply_markup=main_menu(db_user))


@router.message(Command("cancel"))
@router.message(F.text == texts.BTN_CANCEL)
async def cmd_cancel(
    message: Message,
    state: FSMContext,
    db_user: User,
    stickers: StickerService,
) -> None:
    current = await state.get_state()
    await state.clear()
    if current:
        await stickers.send_mood(message.bot, message.chat.id, "deny")
        await message.answer(texts.cancelled(), reply_markup=main_menu(db_user))
    else:
        await message.answer("Нічого скасовувати 💜", reply_markup=main_menu(db_user))
