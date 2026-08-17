from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from bot import texts
from bot.config import DEFAULT_DIGEST_TIME
from bot.db import Database, User
from bot.keyboards import cancel_kb, main_menu
from bot.stickers import StickerService
from bot.utils import parse_digest_time

router = Router(name="reminders_ui")


class DigestForm(StatesGroup):
    time = State()


@router.message(F.text == texts.BTN_DIGEST)
async def digest_menu(
    message: Message,
    db: Database,
    db_user: User,
    stickers: StickerService,
    state: FSMContext,
) -> None:
    if not db_user.is_parent:
        await stickers.send_mood(message.bot, message.chat.id, "deny")
        await message.answer(texts.no_access(), reply_markup=main_menu(db_user))
        return
    current = await db.get_setting("digest_time", DEFAULT_DIGEST_TIME) or DEFAULT_DIGEST_TIME
    await state.set_state(DigestForm.time)
    await message.answer(texts.ask_digest_time(current), reply_markup=cancel_kb())


@router.message(DigestForm.time, F.text)
async def digest_set(
    message: Message,
    state: FSMContext,
    db: Database,
    db_user: User,
    stickers: StickerService,
) -> None:
    text = (message.text or "").strip()
    if text == texts.BTN_CANCEL:
        return
    parsed = parse_digest_time(text)
    if not parsed:
        await stickers.send_mood(message.bot, message.chat.id, "error")
        await message.answer(texts.bad_input())
        return
    await db.set_setting("digest_time", parsed)
    await state.clear()
    await stickers.send_mood(message.bot, message.chat.id, "saved")
    await message.answer(
        texts.digest_updated(parsed),
        reply_markup=main_menu(db_user),
    )
