from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, Update
from aiogram.types import User as TgUser

from bot.db import Database, User


class DbUserMiddleware(BaseMiddleware):
    def __init__(self, db: Database) -> None:
        self.db = db

    def _resolve_tg_user(
        self, event: TelegramObject, data: dict[str, Any]
    ) -> TgUser | None:
        from_user = data.get("event_from_user")
        if isinstance(from_user, TgUser):
            return from_user

        if isinstance(event, Message) and event.from_user:
            return event.from_user
        if isinstance(event, CallbackQuery) and event.from_user:
            return event.from_user
        if isinstance(event, Update):
            if event.message and event.message.from_user:
                return event.message.from_user
            if event.callback_query and event.callback_query.from_user:
                return event.callback_query.from_user
            if event.edited_message and event.edited_message.from_user:
                return event.edited_message.from_user
        return None

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["db"] = self.db
        data.setdefault("user_just_created", False)

        tg_user = self._resolve_tg_user(event, data)
        if tg_user:
            user, created = await self.db.upsert_user(
                telegram_id=tg_user.id,
                username=tg_user.username,
                full_name=tg_user.full_name,
            )
            data["db_user"] = user
            data["user_just_created"] = created

        return await handler(event, data)


def require_admin(user: User) -> bool:
    return bool(user and user.is_admin)


def can_edit_task(user: User, created_by: int | None) -> bool:
    if user.is_parent:
        return True
    return created_by is not None and created_by == user.telegram_id
