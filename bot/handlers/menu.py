from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.keyboards import add_kind_kb

router = Router(name="menu")


class AddFlow(StatesGroup):
    choosing = State()


@router.message(F.text == texts.BTN_ADD)
async def btn_add(message: Message, state: FSMContext) -> None:
    await state.set_state(AddFlow.choosing)
    await message.answer("Що додаємо? ✨", reply_markup=add_kind_kb())


@router.callback_query(F.data.startswith("add:"))
async def add_kind_chosen(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    kind = callback.data.split(":", 1)[1]
    await callback.answer()
    await state.clear()
    # Hand off via state data for task/schedule routers listening on message after redirect
    if not callback.message:
        return
    await state.update_data(pending_add=kind)
    if kind == "task":
        from bot.handlers.tasks import begin_add_task

        await begin_add_task(callback.message, state)
    elif kind in {"weekly", "once"}:
        from bot.handlers.schedule import begin_add_schedule

        await begin_add_schedule(callback.message, state, kind=kind)
    else:
        await callback.message.answer(texts.bad_input())
