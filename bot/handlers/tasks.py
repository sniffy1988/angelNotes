from __future__ import annotations

from datetime import date, datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.config import MAX_REMINDER_OFFSETS, Settings
from bot.db import Database, User
from bot.keyboards import (
    assign_child_kb,
    calendar_month_kb,
    cancel_kb,
    confirm_delete_kb,
    due_kb,
    main_menu,
    remind_preset_kb,
    skip_cancel_kb,
    task_actions_kb,
    task_edit_fields_kb,
    time_preset_kb,
)
from bot.middlewares import can_edit_task
from bot.stickers import StickerService
from bot.utils import (
    compact_time_to_hhmm,
    is_url,
    normalize_offsets,
    parse_due,
    parse_offset_text,
    task_card_html,
    to_iso,
)

router = Router(name="tasks")


class TaskForm(StatesGroup):
    title = State()
    description = State()
    link = State()
    due = State()
    due_time = State()
    assignee = State()
    offsets = State()


async def begin_add_task(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(TaskForm.title)
    await state.update_data(flow="create", offsets=[])
    await message.answer(texts.ask_title("task"), reply_markup=cancel_kb())


@router.message(F.text == texts.BTN_TASKS)
async def list_tasks(
    message: Message,
    db: Database,
    db_user: User,
    settings: Settings,
    stickers: StickerService,
) -> None:
    tasks = await db.list_tasks()
    if not tasks:
        await stickers.send_mood(message.bot, message.chat.id, "empty")
        await message.answer(texts.empty_tasks(), reply_markup=main_menu(db_user))
        return

    users = {u.telegram_id: u for u in await db.list_users()}
    for task in tasks:
        offsets = [o.before_minutes for o in await db.get_offsets("task", task.id)]
        author = None
        if task.created_by and task.created_by in users:
            u = users[task.created_by]
            author = u.full_name or u.username or str(u.telegram_id)
        assignee = None
        if task.assigned_to and task.assigned_to in users:
            au = users[task.assigned_to]
            assignee = au.full_name or au.username or str(au.telegram_id)
        await message.answer(
            task_card_html(task, offsets, settings.tz, author, assignee),
            reply_markup=task_actions_kb(
                task.id,
                can_edit=can_edit_task(db_user, task.created_by),
                is_done=task.status == "done",
            ),
            disable_web_page_preview=True,
        )


@router.message(TaskForm.title, F.text)
async def task_title(
    message: Message,
    state: FSMContext,
    db: Database,
    db_user: User,
    settings: Settings,
    stickers: StickerService,
) -> None:
    title = (message.text or "").strip()
    if not title or title == texts.BTN_CANCEL:
        return
    data = await state.get_data()
    if data.get("flow") == "edit":
        await _save_edit(message, state, db, db_user, settings, stickers, title=title)
        return
    await state.update_data(title=title)
    await state.set_state(TaskForm.description)
    await message.answer(texts.ask_description(), reply_markup=skip_cancel_kb())


@router.message(TaskForm.description, F.text)
async def task_description(
    message: Message,
    state: FSMContext,
    db: Database,
    db_user: User,
    settings: Settings,
    stickers: StickerService,
) -> None:
    text = (message.text or "").strip()
    if text == texts.BTN_CANCEL:
        return
    data = await state.get_data()
    value = None if text == texts.BTN_SKIP else text
    if data.get("flow") == "edit":
        await _save_edit(
            message, state, db, db_user, settings, stickers, description=value
        )
        return
    await state.update_data(description=value)
    await state.set_state(TaskForm.link)
    await message.answer(texts.ask_link(), reply_markup=skip_cancel_kb())


@router.message(TaskForm.link, F.text)
async def task_link(
    message: Message,
    state: FSMContext,
    db: Database,
    db_user: User,
    settings: Settings,
    stickers: StickerService,
) -> None:
    text = (message.text or "").strip()
    if text == texts.BTN_CANCEL:
        return
    if text == texts.BTN_SKIP:
        link = None
    elif is_url(text):
        link = text
    else:
        await stickers.send_mood(message.bot, message.chat.id, "error")
        await message.answer(texts.please_url())
        return

    data = await state.get_data()
    if data.get("flow") == "edit":
        await _save_edit(message, state, db, db_user, settings, stickers, link=link)
        return

    await state.update_data(link=link)
    await state.set_state(TaskForm.due)
    await message.answer(texts.ask_due(), reply_markup=due_kb(required=False))


@router.message(TaskForm.due, F.text != texts.BTN_PICK_DATE)
async def task_due(
    message: Message,
    state: FSMContext,
    db: Database,
    db_user: User,
    settings: Settings,
    stickers: StickerService,
) -> None:
    text = (message.text or "").strip()
    if text == texts.BTN_CANCEL:
        return

    if text in {texts.BTN_NO_DUE, texts.BTN_SKIP}:
        due_iso = None
    else:
        dt = parse_due(text, settings.tz)
        if not dt:
            await stickers.send_mood(message.bot, message.chat.id, "error")
            await message.answer(texts.bad_input())
            return
        due_iso = to_iso(dt)

    await _handle_due_value(message, state, db, db_user, settings, stickers, due_iso)


@router.message(TaskForm.due, F.text == texts.BTN_PICK_DATE)
async def task_due_pick_date(message: Message) -> None:
    now = datetime.now()
    await message.answer(
        "Обери день ✨",
        reply_markup=calendar_month_kb(now.year, now.month, "tcal"),
    )


@router.callback_query(TaskForm.due, F.data == "tcal:noop")
async def task_due_calendar_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(TaskForm.due, F.data.startswith("tcal:nav:"))
async def task_due_calendar_nav(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.message:
        return
    _, _, year_s, month_s = callback.data.split(":")
    await callback.message.edit_reply_markup(
        reply_markup=calendar_month_kb(int(year_s), int(month_s), "tcal")
    )


@router.callback_query(TaskForm.due, F.data.startswith("tcal:day:"))
async def task_due_calendar_day(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await callback.answer()
    if not callback.message:
        return
    selected = callback.data.split(":", 2)[2]
    chosen_day = date.fromisoformat(selected)
    await state.update_data(pending_due_date=selected)
    await state.set_state(TaskForm.due_time)
    await callback.message.answer(
        texts.ask_time_for_date(chosen_day.strftime("%d.%m.%Y")),
        reply_markup=time_preset_kb("tctime"),
    )
    await callback.message.answer("Або напиши час ↓", reply_markup=cancel_kb())


@router.callback_query(TaskForm.due_time, F.data.regexp(r"^tctime:\d{4}$"))
async def task_due_time_cb(
    callback: CallbackQuery,
    state: FSMContext,
    db: Database,
    db_user: User,
    settings: Settings,
    stickers: StickerService,
) -> None:
    await callback.answer()
    if not callback.message:
        return
    compact = callback.data.split(":")[1]
    hhmm = compact_time_to_hhmm(compact)
    if not hhmm:
        return
    data = await state.get_data()
    dt = parse_due(f"{data['pending_due_date']} {hhmm}", settings.tz)
    if not dt:
        await stickers.send_mood(callback.bot, callback.message.chat.id, "error")
        await callback.message.answer(texts.bad_input())
        return
    await _handle_due_value(
        callback.message, state, db, db_user, settings, stickers, to_iso(dt)
    )


@router.message(TaskForm.due_time, F.text)
async def task_due_time(
    message: Message,
    state: FSMContext,
    db: Database,
    db_user: User,
    settings: Settings,
    stickers: StickerService,
) -> None:
    text = (message.text or "").strip()
    if text == texts.BTN_CANCEL:
        return
    data = await state.get_data()
    dt = parse_due(f"{data['pending_due_date']} {text}", settings.tz)
    if not dt:
        await stickers.send_mood(message.bot, message.chat.id, "error")
        await message.answer(texts.bad_input())
        return
    await _handle_due_value(
        message, state, db, db_user, settings, stickers, to_iso(dt)
    )


@router.callback_query(TaskForm.offsets, F.data.startswith("off:"))
async def task_offsets_cb(
    callback: CallbackQuery,
    state: FSMContext,
    db: Database,
    db_user: User,
    settings: Settings,
    stickers: StickerService,
) -> None:
    await callback.answer()
    if not callback.message:
        return
    action = callback.data.split(":", 1)[1]
    data = await state.get_data()
    offsets: list[int] = list(data.get("offsets") or [])

    if action == "cancel":
        await state.clear()
        await stickers.send_mood(callback.bot, callback.message.chat.id, "deny")
        await callback.message.answer(
            texts.cancelled(), reply_markup=main_menu(db_user)
        )
        return

    if action in {"skip", "done"}:
        if action == "skip":
            await state.update_data(offsets=[])
        await _finish_create_or_edit_offsets(
            callback.message, state, db, db_user, settings, stickers
        )
        return

    if action == "more":
        await callback.message.answer(
            texts.ask_remind_offsets(offsets),
            reply_markup=remind_preset_kb(offsets),
        )
        return

    try:
        minutes = int(action)
    except ValueError:
        return

    if minutes in offsets:
        offsets = [m for m in offsets if m != minutes]
    else:
        if len(offsets) >= MAX_REMINDER_OFFSETS:
            await callback.message.answer(
                f"Максимум {MAX_REMINDER_OFFSETS} нагадувань."
            )
            return
        offsets.append(minutes)

    await state.update_data(offsets=offsets)
    try:
        await callback.message.edit_reply_markup(reply_markup=remind_preset_kb(offsets))
    except Exception:
        await callback.message.answer(
            texts.ask_remind_offsets(offsets),
            reply_markup=remind_preset_kb(offsets),
        )


@router.message(TaskForm.offsets, F.text)
async def task_offsets_text(
    message: Message,
    state: FSMContext,
    stickers: StickerService,
) -> None:
    text = (message.text or "").strip()
    if text == texts.BTN_CANCEL:
        return
    minutes = parse_offset_text(text)
    if minutes is None:
        await stickers.send_mood(message.bot, message.chat.id, "error")
        await message.answer(texts.bad_input())
        return
    data = await state.get_data()
    offsets: list[int] = list(data.get("offsets") or [])
    if minutes not in offsets:
        if len(offsets) >= MAX_REMINDER_OFFSETS:
            await message.answer(f"Максимум {MAX_REMINDER_OFFSETS} нагадувань.")
            return
        offsets.append(minutes)
    await state.update_data(offsets=offsets)
    await message.answer(
        texts.ask_remind_offsets(offsets),
        reply_markup=remind_preset_kb(offsets),
    )


async def _finish_create_or_edit_offsets(
    message: Message,
    state: FSMContext,
    db: Database,
    db_user: User,
    settings: Settings,
    stickers: StickerService,
) -> None:
    data = await state.get_data()
    if data.get("flow") == "edit":
        task_id = data["edit_task_id"]
        due_at = data.get("due_at")
        offsets = normalize_offsets(data.get("offsets"), has_due=bool(due_at))
        await db.set_offsets("task", task_id, offsets)
        task = await db.get_task(task_id)
        await state.clear()
        await stickers.send_mood(message.bot, message.chat.id, "saved")
        await message.answer(
            texts.saved_ok() + "\n\n" + task_card_html(task, offsets, settings.tz),
            reply_markup=main_menu(db_user),
            disable_web_page_preview=True,
        )
        return
    await _finish_create(message, state, db, db_user, settings, stickers)


async def _handle_due_value(
    message: Message,
    state: FSMContext,
    db: Database,
    db_user: User,
    settings: Settings,
    stickers: StickerService,
    due_iso: str | None,
) -> None:
    data = await state.get_data()
    if data.get("flow") == "edit":
        task_id = data["edit_task_id"]
        await db.update_task_fields(task_id, due_at=due_iso)
        if due_iso is None:
            await db.set_offsets("task", task_id, [])
        task = await db.get_task(task_id)
        offsets = [o.before_minutes for o in await db.get_offsets("task", task_id)]
        await state.clear()
        await stickers.send_mood(message.bot, message.chat.id, "saved")
        await message.answer(
            texts.saved_ok() + "\n\n" + task_card_html(task, offsets, settings.tz),
            reply_markup=main_menu(db_user),
            disable_web_page_preview=True,
        )
        return

    await state.update_data(due_at=due_iso, offsets=[])
    if db_user.is_parent:
        children = [
            u for u in await db.list_children() if u.telegram_id != db_user.telegram_id
        ]
        if not children:
            await state.update_data(assigned_to=db_user.telegram_id)
            await message.answer(texts.child_not_registered())
        elif len(children) == 1:
            await state.update_data(assigned_to=children[0].telegram_id)
        else:
            await state.set_state(TaskForm.assignee)
            await message.answer(
                texts.ask_assignee(), reply_markup=assign_child_kb(children)
            )
            return
    else:
        await state.update_data(assigned_to=db_user.telegram_id)

    if due_iso is None:
        await _finish_create(message, state, db, db_user, settings, stickers)
        return

    await state.set_state(TaskForm.offsets)
    await message.answer(
        texts.ask_remind_offsets([]),
        reply_markup=remind_preset_kb([]),
    )


async def _finish_create(
    message: Message,
    state: FSMContext,
    db: Database,
    db_user: User,
    settings: Settings,
    stickers: StickerService,
) -> None:
    data = await state.get_data()
    due_at = data.get("due_at")
    offsets = normalize_offsets(data.get("offsets"), has_due=bool(due_at))
    task = await db.create_task(
        title=data["title"],
        description=data.get("description"),
        link=data.get("link"),
        due_at=due_at,
        created_by=db_user.telegram_id,
        assigned_to=data.get("assigned_to"),
        offsets=offsets,
    )
    await state.clear()
    await stickers.send_mood(message.bot, message.chat.id, "saved")
    await message.answer(
        texts.saved_ok() + "\n\n" + task_card_html(task, offsets, settings.tz),
        reply_markup=main_menu(db_user),
        disable_web_page_preview=True,
    )


async def _save_edit(
    message: Message,
    state: FSMContext,
    db: Database,
    db_user: User,
    settings: Settings,
    stickers: StickerService,
    **fields,
) -> None:
    data = await state.get_data()
    task_id = data["edit_task_id"]
    await db.update_task_fields(task_id, **fields)
    task = await db.get_task(task_id)
    offsets = [o.before_minutes for o in await db.get_offsets("task", task_id)]
    await state.clear()
    await stickers.send_mood(message.bot, message.chat.id, "saved")
    await message.answer(
        texts.saved_ok() + "\n\n" + task_card_html(task, offsets, settings.tz),
        reply_markup=main_menu(db_user),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data.startswith("tassign:"))
async def task_assign_create(
    callback: CallbackQuery,
    state: FSMContext,
    db: Database,
    db_user: User,
    settings: Settings,
    stickers: StickerService,
) -> None:
    await callback.answer()
    if not callback.message:
        return
    assigned_to = int(callback.data.split(":")[1])
    await state.update_data(assigned_to=assigned_to)
    data = await state.get_data()
    if data.get("due_at") is None:
        await _finish_create(callback.message, state, db, db_user, settings, stickers)
        return
    await state.set_state(TaskForm.offsets)
    await callback.message.answer(
        texts.ask_remind_offsets([]),
        reply_markup=remind_preset_kb([]),
    )


@router.callback_query(F.data.startswith("tassignedit:"))
async def task_assign_edit(
    callback: CallbackQuery,
    state: FSMContext,
    db: Database,
    db_user: User,
    settings: Settings,
    stickers: StickerService,
) -> None:
    await callback.answer()
    if not callback.message or not db_user.is_parent:
        return
    _, user_id_s, task_id_s = callback.data.split(":", 2)
    task_id = int(task_id_s)
    await db.update_task_fields(task_id, assigned_to=int(user_id_s))
    task = await db.get_task(task_id)
    offsets = [o.before_minutes for o in await db.get_offsets("task", task_id)]
    await state.clear()
    await stickers.send_mood(callback.bot, callback.message.chat.id, "saved")
    await callback.message.answer(
        texts.saved_ok() + "\n\n" + task_card_html(task, offsets, settings.tz),
        reply_markup=main_menu(db_user),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data.startswith("task:done:"))
async def task_done(
    callback: CallbackQuery,
    db: Database,
    db_user: User,
    stickers: StickerService,
) -> None:
    task_id = int(callback.data.split(":")[2])
    task = await db.set_task_status(task_id, "done", db_user.telegram_id)
    await callback.answer()
    if not task or not callback.message:
        return
    await stickers.send_mood(callback.bot, callback.message.chat.id, "done")
    await callback.message.answer(texts.done_ok())
    await callback.message.edit_reply_markup(
        reply_markup=task_actions_kb(
            task.id,
            can_edit=can_edit_task(db_user, task.created_by),
            is_done=True,
        )
    )


@router.callback_query(F.data.startswith("task:reopen:"))
async def task_reopen(
    callback: CallbackQuery,
    db: Database,
    db_user: User,
) -> None:
    task_id = int(callback.data.split(":")[2])
    task = await db.set_task_status(task_id, "open")
    await callback.answer()
    if not task or not callback.message:
        return
    await callback.message.answer(texts.reopen_ok())
    await callback.message.edit_reply_markup(
        reply_markup=task_actions_kb(
            task.id,
            can_edit=can_edit_task(db_user, task.created_by),
            is_done=False,
        )
    )


@router.callback_query(F.data.regexp(r"^task:del:\d+$"))
async def task_del_ask(
    callback: CallbackQuery,
    db: Database,
    db_user: User,
    stickers: StickerService,
) -> None:
    task_id = int(callback.data.split(":")[2])
    task = await db.get_task(task_id)
    await callback.answer()
    if not task or not callback.message:
        return
    if not can_edit_task(db_user, task.created_by):
        await stickers.send_mood(callback.bot, callback.message.chat.id, "deny")
        await callback.message.answer(texts.no_access())
        return
    await callback.message.answer(
        f"Видалити «{task.title}»?",
        reply_markup=confirm_delete_kb("task", task_id),
    )


@router.callback_query(F.data.regexp(r"^task:delok:\d+$"))
async def task_del_ok(
    callback: CallbackQuery,
    db: Database,
    db_user: User,
    stickers: StickerService,
) -> None:
    task_id = int(callback.data.split(":")[2])
    task = await db.get_task(task_id)
    await callback.answer()
    if not task or not callback.message:
        return
    if not can_edit_task(db_user, task.created_by):
        await stickers.send_mood(callback.bot, callback.message.chat.id, "deny")
        await callback.message.answer(texts.no_access())
        return
    await db.delete_task(task_id)
    await callback.message.answer(texts.deleted_ok())


@router.callback_query(F.data.regexp(r"^task:delno:\d+$"))
async def task_del_no(callback: CallbackQuery) -> None:
    await callback.answer("Ок")
    if callback.message:
        await callback.message.answer("Залишила як є 💜")


@router.callback_query(F.data.regexp(r"^task:edit:\d+$"))
async def task_edit_menu(
    callback: CallbackQuery,
    db: Database,
    db_user: User,
    stickers: StickerService,
) -> None:
    task_id = int(callback.data.split(":")[2])
    task = await db.get_task(task_id)
    await callback.answer()
    if not task or not callback.message:
        return
    if not can_edit_task(db_user, task.created_by):
        await stickers.send_mood(callback.bot, callback.message.chat.id, "deny")
        await callback.message.answer(texts.no_access())
        return
    await callback.message.answer(
        texts.edit_choose_field(),
        reply_markup=task_edit_fields_kb(task_id),
    )


@router.callback_query(F.data.startswith("tedit:"))
async def task_edit_field(
    callback: CallbackQuery,
    state: FSMContext,
    db: Database,
    db_user: User,
) -> None:
    _, field, task_id_s = callback.data.split(":", 2)
    task_id = int(task_id_s)
    task = await db.get_task(task_id)
    await callback.answer()
    if not task or not callback.message:
        return
    if not can_edit_task(db_user, task.created_by):
        await callback.message.answer(texts.no_access())
        return

    await state.clear()
    await state.update_data(flow="edit", edit_task_id=task_id)

    if field == "title":
        await state.set_state(TaskForm.title)
        await callback.message.answer(texts.ask_title("task"), reply_markup=cancel_kb())
    elif field == "description":
        await state.set_state(TaskForm.description)
        await callback.message.answer(
            texts.ask_description(), reply_markup=skip_cancel_kb()
        )
    elif field == "link":
        await state.set_state(TaskForm.link)
        await callback.message.answer(texts.ask_link(), reply_markup=skip_cancel_kb())
    elif field == "due":
        await state.set_state(TaskForm.due)
        await callback.message.answer(texts.ask_due(), reply_markup=due_kb())
    elif field == "assignee":
        if not db_user.is_parent:
            await callback.message.answer(texts.no_access())
            return
        children = [u for u in await db.list_children() if u.telegram_id != db_user.telegram_id]
        if not children:
            await callback.message.answer(texts.child_not_registered())
            return
        await state.set_state(TaskForm.assignee)
        await callback.message.answer(
            texts.ask_assignee(), reply_markup=assign_child_kb(children, task_id=task_id)
        )
    elif field == "remind":
        if not task.due_at:
            await callback.message.answer("Спочатку задай строк.")
            return
        offsets = [o.before_minutes for o in await db.get_offsets("task", task_id)]
        await state.set_state(TaskForm.offsets)
        await state.update_data(offsets=offsets, due_at=task.due_at)
        await callback.message.answer(
            texts.ask_remind_offsets(offsets),
            reply_markup=remind_preset_kb(offsets),
        )
