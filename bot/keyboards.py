from __future__ import annotations

import calendar

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from bot import texts
from bot.config import MAX_REMINDER_OFFSETS
from bot.db import User


def main_menu(user: User) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text=texts.BTN_TASKS),
        KeyboardButton(text=texts.BTN_SCHEDULE),
    )
    builder.row(
        KeyboardButton(text=texts.BTN_ADD),
        KeyboardButton(text=texts.BTN_CHAT),
    )
    extra: list[KeyboardButton] = []
    if user.is_parent:
        extra.append(KeyboardButton(text=texts.BTN_DIGEST))
    if user.is_admin:
        extra.append(KeyboardButton(text=texts.BTN_ADMIN))
    if extra:
        builder.row(*extra)
    return builder.as_markup(resize_keyboard=True)


def chat_menu(user: User) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text=texts.BTN_TASKS),
        KeyboardButton(text=texts.BTN_SCHEDULE),
    )
    builder.row(
        KeyboardButton(text=texts.BTN_ADD),
        KeyboardButton(text=texts.BTN_CHAT),
    )
    extra: list[KeyboardButton] = []
    if user.is_parent:
        extra.append(KeyboardButton(text=texts.BTN_DIGEST))
    if user.is_admin:
        extra.append(KeyboardButton(text=texts.BTN_ADMIN))
    if extra:
        builder.row(*extra)
    builder.row(
        KeyboardButton(text=texts.BTN_CHAT_NEW),
        KeyboardButton(text=texts.BTN_CHAT_BYE),
    )
    return builder.as_markup(resize_keyboard=True)


def cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=texts.BTN_CANCEL)]],
        resize_keyboard=True,
    )


def skip_cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=texts.BTN_SKIP)],
            [KeyboardButton(text=texts.BTN_CANCEL)],
        ],
        resize_keyboard=True,
    )


def due_kb(*, required: bool = False) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = [
        [KeyboardButton(text=texts.BTN_PICK_DATE)]
    ]
    if not required:
        rows.append([KeyboardButton(text=texts.BTN_NO_DUE)])
    rows.append([KeyboardButton(text=texts.BTN_CANCEL)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def date_skip_cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=texts.BTN_PICK_DATE)],
            [KeyboardButton(text=texts.BTN_SKIP)],
            [KeyboardButton(text=texts.BTN_CANCEL)],
        ],
        resize_keyboard=True,
    )


def skip_cancel_only_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=texts.BTN_SKIP)],
            [KeyboardButton(text=texts.BTN_CANCEL)],
        ],
        resize_keyboard=True,
    )


def weekday_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for i, label in enumerate(texts.WEEKDAYS_SHORT):
        builder.button(text=label, callback_data=f"wd:{i}")
    builder.adjust(4, 3)
    return builder.as_markup()


def remind_preset_kb(current: list[int]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label, minutes in texts.REMIND_PRESETS:
        mark = "✓ " if minutes in current else ""
        builder.button(text=f"{mark}{label}", callback_data=f"off:{minutes}")
    builder.adjust(2)
    can_more = len(current) < MAX_REMINDER_OFFSETS
    row: list[InlineKeyboardButton] = []
    if can_more and current:
        row.append(
            InlineKeyboardButton(
                text=texts.BTN_MORE_OFFSET,
                callback_data="off:more",
            )
        )
    row.append(
        InlineKeyboardButton(text=texts.BTN_DONE_OFFSETS, callback_data="off:done")
    )
    builder.row(*row)
    builder.row(
        InlineKeyboardButton(text=texts.BTN_SKIP, callback_data="off:skip"),
        InlineKeyboardButton(text=texts.BTN_CANCEL, callback_data="off:cancel"),
    )
    return builder.as_markup()


def add_kind_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Завдання", callback_data="add:task")
    builder.button(text="Урок (щотижня)", callback_data="add:weekly")
    builder.button(text="Подія", callback_data="add:once")
    builder.adjust(1)
    return builder.as_markup()


def task_actions_kb(task_id: int, *, can_edit: bool, is_done: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if is_done:
        builder.button(text="↩ Повернути", callback_data=f"task:reopen:{task_id}")
    else:
        builder.button(text="✔ Зроблено", callback_data=f"task:done:{task_id}")
    if can_edit:
        builder.button(text="✏️ Змінити", callback_data=f"task:edit:{task_id}")
        builder.button(text="🗑 Видалити", callback_data=f"task:del:{task_id}")
    builder.adjust(2)
    return builder.as_markup()


def task_edit_fields_kb(task_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, label in [
        ("title", "Назва"),
        ("description", "Опис"),
        ("link", "Посилання"),
        ("due", "Строк"),
        ("assignee", "Дитина"),
        ("remind", "Нагадування"),
    ]:
        builder.button(text=label, callback_data=f"tedit:{key}:{task_id}")
    builder.adjust(2)
    return builder.as_markup()


def schedule_view_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=texts.BTN_TODAY, callback_data="sch:today")
    builder.button(text=texts.BTN_WEEK, callback_data="sch:week")
    builder.adjust(2)
    return builder.as_markup()


def schedule_actions_kb(item_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Змінити", callback_data=f"sch:edit:{item_id}")
    builder.button(text="🗑 Видалити", callback_data=f"sch:del:{item_id}")
    builder.adjust(2)
    return builder.as_markup()


def schedule_edit_fields_kb(item_id: int, kind: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    fields = [
        ("title", "Назва"),
        ("description", "Опис"),
        ("link", "Посилання"),
        ("remind", "Нагадування"),
    ]
    if kind == "weekly":
        fields.extend(
            [
                ("weekday", "День"),
                ("start_time", "Початок"),
                ("end_time", "Кінець"),
            ]
        )
    else:
        fields.extend(
            [
                ("starts_at", "Початок"),
                ("ends_at", "Кінець"),
            ]
        )
    for key, label in fields:
        builder.button(text=label, callback_data=f"sedit:{key}:{item_id}")
    builder.adjust(2)
    return builder.as_markup()


def confirm_delete_kb(prefix: str, item_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Так, видалити", callback_data=f"{prefix}:delok:{item_id}")
    builder.button(text="Ні", callback_data=f"{prefix}:delno:{item_id}")
    builder.adjust(2)
    return builder.as_markup()


def admin_user_kb(telegram_id: int, role: str, is_admin: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if role == "child":
        builder.button(
            text="→ Батьки",
            callback_data=f"adm:role:parent:{telegram_id}",
        )
    else:
        builder.button(
            text="→ Дитина",
            callback_data=f"adm:role:child:{telegram_id}",
        )
    if is_admin:
        builder.button(
            text="Зняти адміна",
            callback_data=f"adm:admin:0:{telegram_id}",
        )
    else:
        builder.button(
            text="Зробити адміном",
            callback_data=f"adm:admin:1:{telegram_id}",
        )
    builder.adjust(1)
    return builder.as_markup()


def assign_child_kb(children: list[User], *, task_id: int | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    prefix = "tassignedit" if task_id is not None else "tassign"
    for child in children:
        label = child.full_name or child.username or str(child.telegram_id)
        suffix = f":{task_id}" if task_id is not None else ""
        builder.button(text=label, callback_data=f"{prefix}:{child.telegram_id}{suffix}")
    builder.adjust(1)
    return builder.as_markup()


def time_preset_kb(prefix: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label in texts.TIME_PRESETS:
        compact = label.replace(":", "")
        builder.button(text=label, callback_data=f"{prefix}:{compact}")
    builder.adjust(3)
    return builder.as_markup()


def calendar_month_kb(year: int, month: int, prefix: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="←",
            callback_data=f"{prefix}:nav:{_shift_month(year, month, -1)[0]}:{_shift_month(year, month, -1)[1]}",
        ),
        InlineKeyboardButton(text=f"{month:02d}.{year}", callback_data=f"{prefix}:noop"),
        InlineKeyboardButton(
            text="→",
            callback_data=f"{prefix}:nav:{_shift_month(year, month, 1)[0]}:{_shift_month(year, month, 1)[1]}",
        ),
    )
    builder.row(
        *[
            InlineKeyboardButton(text=label, callback_data=f"{prefix}:noop")
            for label in texts.WEEKDAYS_SHORT
        ]
    )
    for week in calendar.monthcalendar(year, month):
        row = []
        for day in week:
            if day == 0:
                row.append(
                    InlineKeyboardButton(text=" ", callback_data=f"{prefix}:noop")
                )
            else:
                row.append(
                    InlineKeyboardButton(
                        text=str(day),
                        callback_data=f"{prefix}:day:{year:04d}-{month:02d}-{day:02d}",
                    )
                )
        builder.row(*row)
    return builder.as_markup()


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    month += delta
    if month < 1:
        return year - 1, 12
    if month > 12:
        return year + 1, 1
    return year, month
