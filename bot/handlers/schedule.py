from __future__ import annotations

from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.config import MAX_REMINDER_OFFSETS, Settings
from bot.db import Database, ScheduleItem, User
from bot.keyboards import (
    cancel_kb,
    confirm_delete_kb,
    main_menu,
    remind_preset_kb,
    schedule_actions_kb,
    schedule_edit_fields_kb,
    schedule_view_kb,
    skip_cancel_kb,
    weekday_kb,
)
from bot.stickers import StickerService
from bot.utils import (
    from_iso,
    is_url,
    normalize_offsets,
    parse_due,
    parse_offset_text,
    parse_time_hhmm,
    schedule_card_html,
    to_iso,
)

router = Router(name="schedule")


class ScheduleForm(StatesGroup):
    title = State()
    description = State()
    link = State()
    weekday = State()
    start_time = State()
    end_time = State()
    starts_at = State()
    ends_at = State()
    offsets = State()


async def begin_add_schedule(
    message: Message, state: FSMContext, *, kind: str
) -> None:
    await state.clear()
    await state.set_state(ScheduleForm.title)
    await state.update_data(flow="create", kind=kind, offsets=[])
    await message.answer(texts.ask_title(kind), reply_markup=cancel_kb())


def _week_bounds(tz, now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or datetime.now(tz)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
        days=now.weekday()
    )
    end = start + timedelta(days=7)
    return start, end


def _item_on_day(item: ScheduleItem, day: datetime, tz) -> bool:
    if item.kind == "weekly":
        return item.weekday == day.weekday()
    if not item.starts_at:
        return False
    return from_iso(item.starts_at, tz).date() == day.date()


def _item_in_week(item: ScheduleItem, start: datetime, end: datetime, tz) -> bool:
    if item.kind == "weekly":
        return True
    if not item.starts_at:
        return False
    starts = from_iso(item.starts_at, tz)
    return start <= starts < end


async def _send_schedule_list(
    message: Message,
    db: Database,
    settings: Settings,
    items: list[ScheduleItem],
    heading: str,
) -> None:
    if not items:
        await message.answer(texts.empty_schedule(), reply_markup=schedule_view_kb())
        return
    await message.answer(heading, reply_markup=schedule_view_kb())
    for item in items:
        offsets = [o.before_minutes for o in await db.get_offsets("schedule", item.id)]
        await message.answer(
            schedule_card_html(item, offsets, settings.tz),
            reply_markup=schedule_actions_kb(item.id),
            disable_web_page_preview=True,
        )


@router.message(F.text == texts.BTN_SCHEDULE)
async def show_schedule(
    message: Message,
    db: Database,
    db_user: User,
    settings: Settings,
    stickers: StickerService,
) -> None:
    items = await db.list_schedule()
    if not items:
        await stickers.send_mood(message.bot, message.chat.id, "empty")
        await message.answer(texts.empty_schedule(), reply_markup=main_menu(db_user))
        return
    start, end = _week_bounds(settings.tz)
    week_items = [i for i in items if _item_in_week(i, start, end, settings.tz)]
    await _send_schedule_list(
        message, db, settings, week_items, "📅 Розклад на цей тиждень:"
    )


@router.callback_query(F.data == "sch:today")
async def sch_today(
    callback: CallbackQuery, db: Database, settings: Settings
) -> None:
    await callback.answer()
    if not callback.message:
        return
    now = datetime.now(settings.tz)
    items = [i for i in await db.list_schedule() if _item_on_day(i, now, settings.tz)]
    await _send_schedule_list(callback.message, db, settings, items, "📅 На сьогодні:")


@router.callback_query(F.data == "sch:week")
async def sch_week(
    callback: CallbackQuery, db: Database, settings: Settings
) -> None:
    await callback.answer()
    if not callback.message:
        return
    start, end = _week_bounds(settings.tz)
    items = [
        i for i in await db.list_schedule() if _item_in_week(i, start, end, settings.tz)
    ]
    await _send_schedule_list(
        callback.message, db, settings, items, "📅 Розклад на цей тиждень:"
    )


@router.message(ScheduleForm.title, F.text)
async def sch_title(
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
        await _save_edit(
            message, state, db, db_user, settings, stickers, title=title
        )
        return
    await state.update_data(title=title)
    await state.set_state(ScheduleForm.description)
    await message.answer(texts.ask_description(), reply_markup=skip_cancel_kb())


@router.message(ScheduleForm.description, F.text)
async def sch_description(
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
    value = None if text == texts.BTN_SKIP else text
    data = await state.get_data()
    if data.get("flow") == "edit":
        await _save_edit(
            message, state, db, db_user, settings, stickers, description=value
        )
        return
    await state.update_data(description=value)
    await state.set_state(ScheduleForm.link)
    await message.answer(texts.ask_link(), reply_markup=skip_cancel_kb())


@router.message(ScheduleForm.link, F.text)
async def sch_link(
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
    if data.get("kind") == "weekly":
        await state.set_state(ScheduleForm.weekday)
        await message.answer(texts.ask_weekday(), reply_markup=weekday_kb())
    else:
        await state.set_state(ScheduleForm.starts_at)
        await message.answer(texts.ask_due_required(), reply_markup=cancel_kb())


@router.callback_query(F.data.startswith("wd:"))
async def sch_weekday(
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
    weekday = int(callback.data.split(":")[1])
    data = await state.get_data()
    if data.get("flow") == "edit":
        await db.update_schedule_fields(data["edit_id"], weekday=weekday)
        item = await db.get_schedule(data["edit_id"])
        offsets = [
            o.before_minutes for o in await db.get_offsets("schedule", data["edit_id"])
        ]
        await state.clear()
        await stickers.send_mood(callback.bot, callback.message.chat.id, "saved")
        await callback.message.answer(
            texts.saved_ok()
            + "\n\n"
            + schedule_card_html(item, offsets, settings.tz),
            reply_markup=main_menu(db_user),
            disable_web_page_preview=True,
        )
        return

    current = await state.get_state()
    if current != ScheduleForm.weekday.state:
        return
    await state.update_data(weekday=weekday)
    await state.set_state(ScheduleForm.start_time)
    await callback.message.answer(texts.ask_start_time(), reply_markup=cancel_kb())


@router.message(ScheduleForm.start_time, F.text)
async def sch_start_time(
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
    parsed = parse_time_hhmm(text)
    if not parsed:
        await stickers.send_mood(message.bot, message.chat.id, "error")
        await message.answer(texts.bad_input())
        return
    data = await state.get_data()
    if data.get("flow") == "edit":
        await _save_edit(
            message, state, db, db_user, settings, stickers, start_time=parsed
        )
        return
    await state.update_data(start_time=parsed)
    await state.set_state(ScheduleForm.end_time)
    await message.answer(texts.ask_end_optional(), reply_markup=skip_cancel_kb())


@router.message(ScheduleForm.end_time, F.text)
async def sch_end_time(
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
        end = None
    else:
        end = parse_time_hhmm(text)
        if not end:
            await stickers.send_mood(message.bot, message.chat.id, "error")
            await message.answer(texts.bad_input())
            return
    data = await state.get_data()
    if data.get("flow") == "edit":
        await _save_edit(
            message, state, db, db_user, settings, stickers, end_time=end
        )
        return
    await state.update_data(end_time=end, offsets=[])
    await state.set_state(ScheduleForm.offsets)
    await message.answer(
        texts.ask_remind_offsets([]),
        reply_markup=remind_preset_kb([]),
    )


@router.message(ScheduleForm.starts_at, F.text)
async def sch_starts_at(
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
    dt = parse_due(text, settings.tz)
    if not dt:
        await stickers.send_mood(message.bot, message.chat.id, "error")
        await message.answer(texts.bad_input())
        return
    data = await state.get_data()
    iso = to_iso(dt)
    if data.get("flow") == "edit":
        await _save_edit(
            message, state, db, db_user, settings, stickers, starts_at=iso
        )
        return
    await state.update_data(starts_at=iso)
    await state.set_state(ScheduleForm.ends_at)
    await message.answer(texts.ask_end_optional(), reply_markup=skip_cancel_kb())


@router.message(ScheduleForm.ends_at, F.text)
async def sch_ends_at(
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
        ends = None
    else:
        dt = parse_due(text, settings.tz)
        if not dt:
            t = parse_time_hhmm(text)
            if t:
                data = await state.get_data()
                base = from_iso(data["starts_at"], settings.tz)
                h, m = map(int, t.split(":"))
                ends = to_iso(base.replace(hour=h, minute=m))
            else:
                await stickers.send_mood(message.bot, message.chat.id, "error")
                await message.answer(texts.bad_input())
                return
        else:
            ends = to_iso(dt)
    data = await state.get_data()
    if data.get("flow") == "edit":
        await _save_edit(
            message, state, db, db_user, settings, stickers, ends_at=ends
        )
        return
    await state.update_data(ends_at=ends, offsets=[])
    await state.set_state(ScheduleForm.offsets)
    await message.answer(
        texts.ask_remind_offsets([]),
        reply_markup=remind_preset_kb([]),
    )


@router.callback_query(ScheduleForm.offsets, F.data.startswith("off:"))
async def sch_offsets_cb(
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
        await _finish_schedule(callback.message, state, db, db_user, settings, stickers)
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


@router.message(ScheduleForm.offsets, F.text)
async def sch_offsets_text(
    message: Message, state: FSMContext, stickers: StickerService
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


async def _finish_schedule(
    message: Message,
    state: FSMContext,
    db: Database,
    db_user: User,
    settings: Settings,
    stickers: StickerService,
) -> None:
    data = await state.get_data()
    offsets = normalize_offsets(data.get("offsets"), has_due=True)

    if data.get("flow") == "edit":
        item_id = data["edit_id"]
        await db.set_offsets("schedule", item_id, offsets)
        item = await db.get_schedule(item_id)
        await state.clear()
        await stickers.send_mood(message.bot, message.chat.id, "saved")
        await message.answer(
            texts.saved_ok()
            + "\n\n"
            + schedule_card_html(item, offsets, settings.tz),
            reply_markup=main_menu(db_user),
            disable_web_page_preview=True,
        )
        return

    kind = data["kind"]
    item = await db.create_schedule(
        kind=kind,
        title=data["title"],
        description=data.get("description"),
        link=data.get("link"),
        weekday=data.get("weekday"),
        start_time=data.get("start_time"),
        end_time=data.get("end_time"),
        starts_at=data.get("starts_at"),
        ends_at=data.get("ends_at"),
        created_by=db_user.telegram_id,
        offsets=offsets,
    )
    await state.clear()
    await stickers.send_mood(message.bot, message.chat.id, "saved")
    await message.answer(
        texts.saved_ok()
        + "\n\n"
        + schedule_card_html(item, offsets, settings.tz),
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
    item_id = data["edit_id"]
    await db.update_schedule_fields(item_id, **fields)
    item = await db.get_schedule(item_id)
    offsets = [o.before_minutes for o in await db.get_offsets("schedule", item_id)]
    await state.clear()
    await stickers.send_mood(message.bot, message.chat.id, "saved")
    await message.answer(
        texts.saved_ok()
        + "\n\n"
        + schedule_card_html(item, offsets, settings.tz),
        reply_markup=main_menu(db_user),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data.regexp(r"^sch:del:\d+$"))
async def sch_del_ask(callback: CallbackQuery, db: Database) -> None:
    item_id = int(callback.data.split(":")[2])
    item = await db.get_schedule(item_id)
    await callback.answer()
    if not item or not callback.message:
        return
    await callback.message.answer(
        f"Видалити «{item.title}»?",
        reply_markup=confirm_delete_kb("sch", item_id),
    )


@router.callback_query(F.data.regexp(r"^sch:delok:\d+$"))
async def sch_del_ok(callback: CallbackQuery, db: Database) -> None:
    item_id = int(callback.data.split(":")[2])
    await callback.answer()
    await db.delete_schedule(item_id)
    if callback.message:
        await callback.message.answer(texts.deleted_ok())


@router.callback_query(F.data.regexp(r"^sch:delno:\d+$"))
async def sch_del_no(callback: CallbackQuery) -> None:
    await callback.answer("Ок")
    if callback.message:
        await callback.message.answer("Залишила як є 💜")


@router.callback_query(F.data.regexp(r"^sch:edit:\d+$"))
async def sch_edit_menu(callback: CallbackQuery, db: Database) -> None:
    item_id = int(callback.data.split(":")[2])
    item = await db.get_schedule(item_id)
    await callback.answer()
    if not item or not callback.message:
        return
    await callback.message.answer(
        texts.edit_choose_field(),
        reply_markup=schedule_edit_fields_kb(item_id, item.kind),
    )


@router.callback_query(F.data.startswith("sedit:"))
async def sch_edit_field(
    callback: CallbackQuery,
    state: FSMContext,
    db: Database,
) -> None:
    _, field, item_id_s = callback.data.split(":", 2)
    item_id = int(item_id_s)
    item = await db.get_schedule(item_id)
    await callback.answer()
    if not item or not callback.message:
        return

    await state.clear()
    await state.update_data(flow="edit", edit_id=item_id, kind=item.kind)

    prompts = {
        "title": (ScheduleForm.title, texts.ask_title(item.kind), cancel_kb()),
        "description": (
            ScheduleForm.description,
            texts.ask_description(),
            skip_cancel_kb(),
        ),
        "link": (ScheduleForm.link, texts.ask_link(), skip_cancel_kb()),
        "start_time": (
            ScheduleForm.start_time,
            texts.ask_start_time(),
            cancel_kb(),
        ),
        "end_time": (
            ScheduleForm.end_time,
            texts.ask_end_optional(),
            skip_cancel_kb(),
        ),
        "starts_at": (
            ScheduleForm.starts_at,
            texts.ask_due_required(),
            cancel_kb(),
        ),
        "ends_at": (
            ScheduleForm.ends_at,
            texts.ask_end_optional(),
            skip_cancel_kb(),
        ),
    }

    if field == "weekday":
        await state.set_state(ScheduleForm.weekday)
        await callback.message.answer(texts.ask_weekday(), reply_markup=weekday_kb())
        return

    if field == "remind":
        offsets = [o.before_minutes for o in await db.get_offsets("schedule", item_id)]
        await state.set_state(ScheduleForm.offsets)
        await state.update_data(offsets=offsets)
        await callback.message.answer(
            texts.ask_remind_offsets(offsets),
            reply_markup=remind_preset_kb(offsets),
        )
        return

    if field in prompts:
        st, prompt, kb = prompts[field]
        await state.set_state(st)
        await callback.message.answer(prompt, reply_markup=kb)
