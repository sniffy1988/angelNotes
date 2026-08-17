from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import aiosqlite

from bot.config import DEFAULT_DIGEST_TIME

Role = Literal["parent", "child"]
TargetType = Literal["task", "schedule"]
ScheduleKind = Literal["weekly", "once"]
TaskStatus = Literal["open", "done"]


@dataclass(slots=True)
class User:
    telegram_id: int
    username: str | None
    full_name: str | None
    role: Role
    is_admin: bool
    created_at: str

    @property
    def is_parent(self) -> bool:
        return self.role == "parent"


@dataclass(slots=True)
class Task:
    id: int
    title: str
    description: str | None
    link: str | None
    status: TaskStatus
    due_at: str | None
    created_by: int | None
    completed_by: int | None
    created_at: str
    completed_at: str | None


@dataclass(slots=True)
class ScheduleItem:
    id: int
    kind: ScheduleKind
    title: str
    description: str | None
    link: str | None
    weekday: int | None
    start_time: str | None
    end_time: str | None
    starts_at: str | None
    ends_at: str | None
    created_by: int | None
    created_at: str


@dataclass(slots=True)
class ReminderOffset:
    id: int
    target_type: TargetType
    target_id: int
    before_minutes: int
    last_sent_occurrence: str | None


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _row_user(row: aiosqlite.Row) -> User:
    return User(
        telegram_id=row["telegram_id"],
        username=row["username"],
        full_name=row["full_name"],
        role=row["role"],
        is_admin=bool(row["is_admin"]),
        created_at=row["created_at"],
    )


def _row_task(row: aiosqlite.Row) -> Task:
    return Task(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        link=row["link"],
        status=row["status"],
        due_at=row["due_at"],
        created_by=row["created_by"],
        completed_by=row["completed_by"],
        created_at=row["created_at"],
        completed_at=row["completed_at"],
    )


def _row_schedule(row: aiosqlite.Row) -> ScheduleItem:
    return ScheduleItem(
        id=row["id"],
        kind=row["kind"],
        title=row["title"],
        description=row["description"],
        link=row["link"],
        weekday=row["weekday"],
        start_time=row["start_time"],
        end_time=row["end_time"],
        starts_at=row["starts_at"],
        ends_at=row["ends_at"],
        created_by=row["created_by"],
        created_at=row["created_at"],
    )


def _row_offset(row: aiosqlite.Row) -> ReminderOffset:
    return ReminderOffset(
        id=row["id"],
        target_type=row["target_type"],
        target_id=row["target_id"],
        before_minutes=row["before_minutes"],
        last_sent_occurrence=row["last_sent_occurrence"],
    )


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self.init_schema()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not connected")
        return self._conn

    async def init_schema(self) -> None:
        await self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                role TEXT NOT NULL DEFAULT 'child',
                is_admin INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                link TEXT,
                status TEXT NOT NULL DEFAULT 'open',
                due_at TEXT,
                created_by INTEGER,
                completed_by INTEGER,
                created_at TEXT NOT NULL,
                completed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS schedule_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                link TEXT,
                weekday INTEGER,
                start_time TEXT,
                end_time TEXT,
                starts_at TEXT,
                ends_at TEXT,
                created_by INTEGER,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS reminder_offsets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_type TEXT NOT NULL,
                target_id INTEGER NOT NULL,
                before_minutes INTEGER NOT NULL,
                last_sent_occurrence TEXT,
                UNIQUE (target_type, target_id, before_minutes)
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        await self.conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            ("digest_time", DEFAULT_DIGEST_TIME),
        )
        await self.conn.commit()

    async def upsert_user(
        self,
        telegram_id: int,
        username: str | None,
        full_name: str | None,
    ) -> User:
        existing = await self.get_user(telegram_id)
        if existing:
            await self.conn.execute(
                """
                UPDATE users
                SET username = ?, full_name = ?
                WHERE telegram_id = ?
                """,
                (username, full_name, telegram_id),
            )
            await self.conn.commit()
            return await self.get_user(telegram_id)  # type: ignore[return-value]

        admin_count = await self.count_admins()
        is_admin = 1 if admin_count == 0 else 0
        await self.conn.execute(
            """
            INSERT INTO users (telegram_id, username, full_name, role, is_admin, created_at)
            VALUES (?, ?, ?, 'child', ?, ?)
            """,
            (telegram_id, username, full_name, is_admin, _now_iso()),
        )
        await self.conn.commit()
        return await self.get_user(telegram_id)  # type: ignore[return-value]

    async def get_user(self, telegram_id: int) -> User | None:
        cur = await self.conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?",
            (telegram_id,),
        )
        row = await cur.fetchone()
        return _row_user(row) if row else None

    async def list_users(self) -> list[User]:
        cur = await self.conn.execute(
            "SELECT * FROM users ORDER BY created_at ASC"
        )
        rows = await cur.fetchall()
        return [_row_user(r) for r in rows]

    async def count_admins(self) -> int:
        cur = await self.conn.execute(
            "SELECT COUNT(*) AS c FROM users WHERE is_admin = 1"
        )
        row = await cur.fetchone()
        return int(row["c"]) if row else 0

    async def set_role(self, telegram_id: int, role: Role) -> User | None:
        await self.conn.execute(
            "UPDATE users SET role = ? WHERE telegram_id = ?",
            (role, telegram_id),
        )
        await self.conn.commit()
        return await self.get_user(telegram_id)

    async def set_admin(self, telegram_id: int, is_admin: bool) -> User | None:
        await self.conn.execute(
            "UPDATE users SET is_admin = ? WHERE telegram_id = ?",
            (1 if is_admin else 0, telegram_id),
        )
        await self.conn.commit()
        return await self.get_user(telegram_id)

    async def get_setting(self, key: str, default: str | None = None) -> str | None:
        cur = await self.conn.execute(
            "SELECT value FROM settings WHERE key = ?",
            (key,),
        )
        row = await cur.fetchone()
        if row:
            return row["value"]
        return default

    async def set_setting(self, key: str, value: str) -> None:
        await self.conn.execute(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        await self.conn.commit()

    async def create_task(
        self,
        *,
        title: str,
        description: str | None,
        link: str | None,
        due_at: str | None,
        created_by: int,
        offsets: list[int],
    ) -> Task:
        cur = await self.conn.execute(
            """
            INSERT INTO tasks (
                title, description, link, status, due_at,
                created_by, created_at
            ) VALUES (?, ?, ?, 'open', ?, ?, ?)
            """,
            (title, description, link, due_at, created_by, _now_iso()),
        )
        task_id = cur.lastrowid
        assert task_id is not None
        if due_at and offsets:
            await self._replace_offsets("task", task_id, offsets)
        await self.conn.commit()
        task = await self.get_task(task_id)
        assert task is not None
        return task

    async def get_task(self, task_id: int) -> Task | None:
        cur = await self.conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = await cur.fetchone()
        return _row_task(row) if row else None

    async def list_tasks(self, status: TaskStatus | None = None) -> list[Task]:
        if status:
            cur = await self.conn.execute(
                "SELECT * FROM tasks WHERE status = ? ORDER BY id DESC",
                (status,),
            )
        else:
            cur = await self.conn.execute(
                "SELECT * FROM tasks ORDER BY CASE status WHEN 'open' THEN 0 ELSE 1 END, id DESC"
            )
        rows = await cur.fetchall()
        return [_row_task(r) for r in rows]

    async def update_task_fields(self, task_id: int, **fields: Any) -> Task | None:
        if not fields:
            return await self.get_task(task_id)
        cols = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [task_id]
        await self.conn.execute(
            f"UPDATE tasks SET {cols} WHERE id = ?",
            values,
        )
        await self.conn.commit()
        return await self.get_task(task_id)

    async def set_task_status(
        self,
        task_id: int,
        status: TaskStatus,
        user_id: int | None = None,
    ) -> Task | None:
        if status == "done":
            await self.conn.execute(
                """
                UPDATE tasks
                SET status = 'done', completed_by = ?, completed_at = ?
                WHERE id = ?
                """,
                (user_id, _now_iso(), task_id),
            )
        else:
            await self.conn.execute(
                """
                UPDATE tasks
                SET status = 'open', completed_by = NULL, completed_at = NULL
                WHERE id = ?
                """,
                (task_id,),
            )
        await self.conn.commit()
        return await self.get_task(task_id)

    async def delete_task(self, task_id: int) -> None:
        await self.conn.execute(
            "DELETE FROM reminder_offsets WHERE target_type = 'task' AND target_id = ?",
            (task_id,),
        )
        await self.conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        await self.conn.commit()

    async def create_schedule(
        self,
        *,
        kind: ScheduleKind,
        title: str,
        description: str | None,
        link: str | None,
        weekday: int | None,
        start_time: str | None,
        end_time: str | None,
        starts_at: str | None,
        ends_at: str | None,
        created_by: int,
        offsets: list[int],
    ) -> ScheduleItem:
        cur = await self.conn.execute(
            """
            INSERT INTO schedule_items (
                kind, title, description, link, weekday, start_time, end_time,
                starts_at, ends_at, created_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                kind,
                title,
                description,
                link,
                weekday,
                start_time,
                end_time,
                starts_at,
                ends_at,
                created_by,
                _now_iso(),
            ),
        )
        item_id = cur.lastrowid
        assert item_id is not None
        if offsets:
            await self._replace_offsets("schedule", item_id, offsets)
        await self.conn.commit()
        item = await self.get_schedule(item_id)
        assert item is not None
        return item

    async def get_schedule(self, item_id: int) -> ScheduleItem | None:
        cur = await self.conn.execute(
            "SELECT * FROM schedule_items WHERE id = ?",
            (item_id,),
        )
        row = await cur.fetchone()
        return _row_schedule(row) if row else None

    async def list_schedule(self) -> list[ScheduleItem]:
        cur = await self.conn.execute(
            """
            SELECT * FROM schedule_items
            ORDER BY
                CASE kind WHEN 'weekly' THEN 0 ELSE 1 END,
                weekday ASC,
                start_time ASC,
                starts_at ASC,
                id ASC
            """
        )
        rows = await cur.fetchall()
        return [_row_schedule(r) for r in rows]

    async def update_schedule_fields(
        self, item_id: int, **fields: Any
    ) -> ScheduleItem | None:
        if not fields:
            return await self.get_schedule(item_id)
        cols = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [item_id]
        await self.conn.execute(
            f"UPDATE schedule_items SET {cols} WHERE id = ?",
            values,
        )
        await self.conn.commit()
        return await self.get_schedule(item_id)

    async def delete_schedule(self, item_id: int) -> None:
        await self.conn.execute(
            "DELETE FROM reminder_offsets WHERE target_type = 'schedule' AND target_id = ?",
            (item_id,),
        )
        await self.conn.execute(
            "DELETE FROM schedule_items WHERE id = ?",
            (item_id,),
        )
        await self.conn.commit()

    async def _replace_offsets(
        self,
        target_type: TargetType,
        target_id: int,
        offsets: list[int],
    ) -> None:
        await self.conn.execute(
            "DELETE FROM reminder_offsets WHERE target_type = ? AND target_id = ?",
            (target_type, target_id),
        )
        for minutes in sorted(set(offsets)):
            await self.conn.execute(
                """
                INSERT INTO reminder_offsets (
                    target_type, target_id, before_minutes, last_sent_occurrence
                ) VALUES (?, ?, ?, NULL)
                """,
                (target_type, target_id, minutes),
            )

    async def set_offsets(
        self,
        target_type: TargetType,
        target_id: int,
        offsets: list[int],
    ) -> list[ReminderOffset]:
        await self._replace_offsets(target_type, target_id, offsets)
        await self.conn.commit()
        return await self.get_offsets(target_type, target_id)

    async def get_offsets(
        self,
        target_type: TargetType,
        target_id: int,
    ) -> list[ReminderOffset]:
        cur = await self.conn.execute(
            """
            SELECT * FROM reminder_offsets
            WHERE target_type = ? AND target_id = ?
            ORDER BY before_minutes DESC
            """,
            (target_type, target_id),
        )
        rows = await cur.fetchall()
        return [_row_offset(r) for r in rows]

    async def list_all_offsets(self) -> list[ReminderOffset]:
        cur = await self.conn.execute("SELECT * FROM reminder_offsets")
        rows = await cur.fetchall()
        return [_row_offset(r) for r in rows]

    async def mark_offset_sent(
        self,
        offset_id: int,
        occurrence_iso: str,
    ) -> None:
        await self.conn.execute(
            """
            UPDATE reminder_offsets
            SET last_sent_occurrence = ?
            WHERE id = ?
            """,
            (occurrence_iso, offset_id),
        )
        await self.conn.commit()
