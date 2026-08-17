from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.db import Database, User
from bot.keyboards import admin_user_kb, main_menu
from bot.stickers import StickerService

router = Router(name="admin")


def _user_line(u: User) -> str:
    name = u.full_name or "—"
    uname = f"@{u.username}" if u.username else "—"
    return (
        f"<b>{name}</b> ({uname})\n"
        f"id: <code>{u.telegram_id}</code>\n"
        f"роль: {texts.role_label(u.role)} · адмін: {texts.admin_yes_no(u.is_admin)}"
    )


async def _show_admin_panel(message: Message, db: Database) -> None:
    users = await db.list_users()
    await message.answer("🛡 Адмін-панель Куромі")
    for u in users:
        await message.answer(
            _user_line(u),
            reply_markup=admin_user_kb(u.telegram_id, u.role, u.is_admin),
        )


@router.message(Command("admin"))
@router.message(F.text == texts.BTN_ADMIN)
async def admin_panel(
    message: Message,
    db: Database,
    db_user: User,
    stickers: StickerService,
) -> None:
    if not db_user.is_admin:
        await stickers.send_mood(message.bot, message.chat.id, "deny")
        await message.answer(texts.no_access(), reply_markup=main_menu(db_user))
        return
    await _show_admin_panel(message, db)


@router.callback_query(F.data.startswith("adm:role:"))
async def admin_set_role(
    callback: CallbackQuery,
    db: Database,
    db_user: User,
    stickers: StickerService,
) -> None:
    await callback.answer()
    if not db_user.is_admin:
        if callback.message:
            await stickers.send_mood(callback.bot, callback.message.chat.id, "deny")
            await callback.message.answer(texts.no_access())
        return
    _, _, role, tid_s = callback.data.split(":", 3)
    tid = int(tid_s)
    if role not in {"parent", "child"}:
        return
    user = await db.set_role(tid, role)  # type: ignore[arg-type]
    if callback.message and user:
        await callback.message.edit_text(
            _user_line(user),
            reply_markup=admin_user_kb(user.telegram_id, user.role, user.is_admin),
        )
        await callback.message.answer(texts.saved_ok())


@router.callback_query(F.data.startswith("adm:admin:"))
async def admin_set_flag(
    callback: CallbackQuery,
    db: Database,
    db_user: User,
    stickers: StickerService,
) -> None:
    await callback.answer()
    if not db_user.is_admin:
        if callback.message:
            await stickers.send_mood(callback.bot, callback.message.chat.id, "deny")
            await callback.message.answer(texts.no_access())
        return
    _, _, flag_s, tid_s = callback.data.split(":", 3)
    tid = int(tid_s)
    make_admin = flag_s == "1"

    if not make_admin and tid == db_user.telegram_id:
        if await db.count_admins() <= 1:
            if callback.message:
                await stickers.send_mood(
                    callback.bot, callback.message.chat.id, "deny"
                )
                await callback.message.answer(
                    "Не можу зняти адміна з останнього адміна 💀"
                )
            return

    user = await db.set_admin(tid, make_admin)
    if callback.message and user:
        await callback.message.edit_text(
            _user_line(user),
            reply_markup=admin_user_kb(user.telegram_id, user.role, user.is_admin),
        )
        await callback.message.answer(texts.saved_ok())
