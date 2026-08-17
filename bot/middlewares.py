from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.db import Database, User


class DbUserMiddleware(BaseMiddleware):
    def __init__(self, db: Database) -> None:
        self.db = db

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["db"] = self.db
        user = None
        tg_user = None
        if isinstance(event, Message) and event.from_user:
            tg_user = event.from_user
        elif isinstance(event, CallbackQuery) and event.from_user:
            tg_user = event.from_user

        if tg_user:
            user = await self.db.upsert_user(
                telegram_id=tg_user.id,
                username=tg_user.username,
                full_name=tg_user.full_name,
            )
            data["db_user"] = user
        return await handler(event, data)


def require_admin(user: User) -> bool:
    return bool(user and user.is_admin)


def can_edit_task(user: User, created_by: int | None) -> bool:
    if user.is_parent:
        return True
    return created_by is not None and created_by == user.telegram_id
