from __future__ import annotations

# Reply menu labels
BTN_TASKS = "💜 Справи"
BTN_SCHEDULE = "📅 Розклад"
BTN_ADD = "✨ Додати"
BTN_DIGEST = "🔔 Нагадування"
BTN_ADMIN = "🛡 Адмін"
BTN_CANCEL = "Скасувати"
BTN_SKIP = "Пропустити"
BTN_NO_DUE = "Без строку"
BTN_DONE_OFFSETS = "Готово"
BTN_MORE_OFFSET = "Ще одне"
BTN_TODAY = "Сьогодні"
BTN_WEEK = "Тиждень"

ROLE_PARENT = "батьки"
ROLE_CHILD = "дитина"

WEEKDAYS_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]
WEEKDAYS_FULL = [
    "понеділок",
    "вівторок",
    "середа",
    "четвер",
    "п’ятниця",
    "субота",
    "неділя",
]

REMIND_PRESETS = [
    ("У строк", 0),
    ("За 10 хв", 10),
    ("За 30 хв", 30),
    ("За 1 год", 60),
    ("За 1 день", 1440),
    ("За 1 тиждень", 10080),
]


def start_message(full_name: str, telegram_id: int, is_admin: bool) -> str:
    admin_hint = "\nТи перший тут — зробила тебе адміном 🛡" if is_admin else ""
    return (
        f"Хе-хе, привіт, {full_name or 'друже'}! 💜\n"
        f"Я Куромі — веду ваші справи й розклад.\n\n"
        f"Твій Telegram ID: <code>{telegram_id}</code>"
        f"{admin_hint}\n\n"
        "Обирай кнопки внизу — і поїхали ✨"
    )


def help_message() -> str:
    return (
        "Я Куромі 🖤\n\n"
        f"{BTN_TASKS} — спільні справи\n"
        f"{BTN_SCHEDULE} — уроки й події\n"
        f"{BTN_ADD} — нове завдання / урок / подія\n"
        f"{BTN_DIGEST} — час вечірнього дайджесту (для батьків)\n"
        f"{BTN_ADMIN} — керування ролями (для адміна)\n\n"
        "/cancel — скасувати введення"
    )


def cancelled() -> str:
    return "Добре, скасувала. Don't be silly — наступного разу впораємось 💜"


def no_access() -> str:
    return "Хе-хе, ні-ні. Немає доступу 💀"


def bad_input() -> str:
    return "What?! Не зрозуміла. Спробуй ще раз 💜"


def please_url() -> str:
    return "Please? Потрібне посилання на кшталт https://... або натисни «Пропустити»."


def empty_tasks() -> str:
    return "Huh? Справ поки немає. Додай через «✨ Додати» 💜"


def empty_schedule() -> str:
    return "Huh? Розклад порожній. Додай урок або подію ✨"


def ask_title(kind: str) -> str:
    labels = {
        "task": "Назва справи?",
        "weekly": "Назва уроку? (наприклад, Математика)",
        "once": "Назва події?",
    }
    return labels.get(kind, "Назва?")


def ask_description() -> str:
    return "Опис? Можна пропустити."


def ask_link() -> str:
    return "Посилання (https://...)? Можна пропустити."


def ask_due() -> str:
    return (
        "Строк? Наприклад: <code>17.08 18:00</code> або <code>завтра 9:00</code>.\n"
        "Або «Без строку»."
    )


def ask_due_required() -> str:
    return (
        "Коли починається? Наприклад: <code>20.08 18:00</code> або <code>завтра 9:00</code>."
    )


def ask_end_optional() -> str:
    return "Час кінця (HH:MM або дата+час)? Можна пропустити."


def ask_weekday() -> str:
    return "Який день тижня?"


def ask_start_time() -> str:
    return "Час початку? Наприклад: <code>9:00</code>"


def ask_remind_offsets(current: list[int] | None = None) -> str:
    base = (
        "Коли нагадати? Обери пресет або напиши на кшталт <code>за 2 години</code>.\n"
        "Можна кілька нагадувань (макс. 5). Потім «Готово»."
    )
    if current:
        return f"{base}\n\nЗараз: {format_offsets(current)}"
    return base


def ask_digest_time(current: str) -> str:
    return (
        f"Зараз дайджест о <b>{current}</b>.\n"
        "Напиши новий час, наприклад <code>20:00</code>."
    )


def digest_updated(value: str) -> str:
    return f"Зберегла: дайджест о {value} 💜"


def saved_ok() -> str:
    return "Thanks! Зберегла ✨"


def done_ok() -> str:
    return "Nice work! Позначила як зроблено ✔"


def reopen_ok() -> str:
    return "Повернула в хід ↩"


def deleted_ok() -> str:
    return "Видалила. Хе-хе 🖤"


def edit_choose_field() -> str:
    return "Що змінити?"


def remind_message(title: str, when_label: str, extra: str = "") -> str:
    body = f"Хе-хе, час настав: <b>{title}</b> — {when_label} 💜"
    if extra:
        return f"{body}\n{extra}"
    return body


def digest_header() -> str:
    return "Вечірній дайджест від Куромі 💤"


def format_offsets(minutes_list: list[int]) -> str:
    if not minutes_list:
        return "немає"
    return ", ".join(format_offset(m) for m in sorted(minutes_list, reverse=True))


def format_offset(minutes: int) -> str:
    if minutes == 0:
        return "у строк"
    if minutes < 60:
        return f"за {minutes} хв"
    if minutes < 1440:
        hours = minutes // 60
        rest = minutes % 60
        if rest:
            return f"за {hours} год {rest} хв"
        return f"за {hours} год"
    days = minutes // 1440
    rest = minutes % 1440
    if rest == 0:
        return f"за {days} дн"
    hours = rest // 60
    if hours:
        return f"за {days} дн {hours} год"
    return f"за {days} дн"


def role_label(role: str) -> str:
    return ROLE_PARENT if role == "parent" else ROLE_CHILD


def admin_yes_no(is_admin: bool) -> str:
    return "так" if is_admin else "ні"
