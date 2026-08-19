from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ChatAction
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from bot import texts
from bot.db import User
from bot.keyboards import chat_menu, main_menu
from bot.llm import (
    ChatMessage,
    OllamaClient,
    OllamaError,
    OllamaModelError,
    OllamaTimeoutError,
    OllamaUnavailableError,
    append_turn,
)
from bot.stickers import StickerService

router = Router(name="chat")

CHAT_HISTORY_KEY = "chat_history"


class ChatForm(StatesGroup):
    active = State()


def _build_messages(history: list[ChatMessage], user_text: str) -> list[ChatMessage]:
    return [
        {"role": "system", "content": texts.KUROMI_SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": user_text},
    ]


async def _enter_chat(
    message: Message,
    state: FSMContext,
    db_user: User,
    stickers: StickerService,
    *,
    reset_history: bool = True,
) -> None:
    if reset_history:
        await state.update_data({CHAT_HISTORY_KEY: []})
    await state.set_state(ChatForm.active)
    await stickers.send_mood(message.bot, message.chat.id, "start")
    await message.answer(
        texts.chat_welcome(),
        reply_markup=chat_menu(db_user),
    )


@router.message(F.text == texts.BTN_CHAT)
async def btn_chat(
    message: Message,
    state: FSMContext,
    db_user: User,
    stickers: StickerService,
) -> None:
    await _enter_chat(message, state, db_user, stickers, reset_history=True)


@router.message(F.text == texts.BTN_CHAT_BYE)
async def btn_chat_bye(
    message: Message,
    state: FSMContext,
    db_user: User,
) -> None:
    current = await state.get_state()
    await state.clear()
    if current == ChatForm.active.state:
        await message.answer(texts.chat_bye(), reply_markup=main_menu(db_user))
    else:
        await message.answer("Ми й так не в чаті 💜", reply_markup=main_menu(db_user))


@router.message(F.text == texts.BTN_CHAT_NEW)
async def btn_chat_new(
    message: Message,
    state: FSMContext,
    db_user: User,
) -> None:
    current = await state.get_state()
    if current != ChatForm.active.state:
        await message.answer("Спочатку натисни «🖤 Поговорити» 💜", reply_markup=main_menu(db_user))
        return
    await state.update_data({CHAT_HISTORY_KEY: []})
    await message.answer(texts.chat_new_conversation(), reply_markup=chat_menu(db_user))


@router.message(ChatForm.active, F.text)
async def chat_message(
    message: Message,
    state: FSMContext,
    db_user: User,
    llm: OllamaClient,
    stickers: StickerService,
) -> None:
    if not message.text:
        return

    user_text = message.text.strip()
    if not user_text:
        await message.answer(texts.bad_input(), reply_markup=chat_menu(db_user))
        return

    data = await state.get_data()
    history: list[ChatMessage] = list(data.get(CHAT_HISTORY_KEY, []))
    payload = _build_messages(history, user_text)

    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    try:
        reply = await llm.chat(payload)
    except OllamaUnavailableError:
        await stickers.send_mood(message.bot, message.chat.id, "error")
        await message.answer(texts.chat_llm_unavailable(), reply_markup=chat_menu(db_user))
        return
    except OllamaTimeoutError:
        await stickers.send_mood(message.bot, message.chat.id, "error")
        await message.answer(texts.chat_llm_timeout(), reply_markup=chat_menu(db_user))
        return
    except OllamaModelError:
        await stickers.send_mood(message.bot, message.chat.id, "error")
        await message.answer(texts.chat_llm_unavailable(), reply_markup=chat_menu(db_user))
        return
    except OllamaError:
        await stickers.send_mood(message.bot, message.chat.id, "error")
        await message.answer(texts.chat_llm_error(), reply_markup=chat_menu(db_user))
        return

    await state.update_data(
        {CHAT_HISTORY_KEY: append_turn(history, user_text, reply)}
    )
    await message.answer(reply, parse_mode=None, reply_markup=chat_menu(db_user))
