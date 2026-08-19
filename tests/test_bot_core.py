"""Core functional checks for angelNotes bot (no Telegram network)."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

from bot.db import Database, ScheduleItem
from bot.handlers import schedule as schedule_handlers
from bot.llm import (
    OllamaClient,
    OllamaError,
    OllamaModelError,
    OllamaTimeoutError,
    OllamaUnavailableError,
    append_turn,
    parse_chat_response,
    trim_history,
    truncate_response,
)
from bot.middlewares import can_edit_task
from bot.utils import (
    from_iso,
    is_url,
    next_weekly_occurrence,
    normalize_offsets,
    parse_digest_time,
    parse_due,
    parse_offset_text,
    parse_time_hhmm,
    to_iso,
)

TZ = ZoneInfo("Europe/Kyiv")


class UtilsTests(unittest.TestCase):
    def test_url(self) -> None:
        self.assertTrue(is_url("https://example.com/x"))
        self.assertFalse(is_url("not-a-url"))
        self.assertFalse(is_url("ftp://x"))

    def test_time_and_digest(self) -> None:
        self.assertEqual(parse_time_hhmm("9:00"), "09:00")
        self.assertEqual(parse_time_hhmm("09.30"), "09:30")
        self.assertIsNone(parse_time_hhmm("25:00"))
        self.assertEqual(parse_digest_time("20:00"), "20:00")

    def test_parse_due_variants(self) -> None:
        now = datetime(2026, 8, 17, 12, 0, tzinfo=TZ)
        d1 = parse_due("17.08 18:00", TZ, now=now)
        assert d1 is not None
        self.assertEqual(d1.hour, 18)
        self.assertEqual(d1.day, 17)

        d2 = parse_due("завтра 9:00", TZ, now=now)
        assert d2 is not None
        self.assertEqual(d2.date(), (now + timedelta(days=1)).date())
        self.assertEqual(d2.hour, 9)

        d3 = parse_due("2026-08-19 18:30", TZ, now=now)
        assert d3 is not None
        self.assertEqual((d3.year, d3.month, d3.day, d3.hour, d3.minute), (2026, 8, 19, 18, 30))

        d4 = parse_due("19-08", TZ, now=now)
        assert d4 is not None
        self.assertEqual((d4.day, d4.month, d4.hour, d4.minute), (19, 8, 9, 0))

    def test_parse_offsets(self) -> None:
        self.assertEqual(parse_offset_text("у строк"), 0)
        self.assertEqual(parse_offset_text("за 10 хв"), 10)
        self.assertEqual(parse_offset_text("за 2 години"), 120)
        self.assertEqual(parse_offset_text("за 1 день"), 1440)
        self.assertEqual(parse_offset_text("за 1 тиждень"), 10080)
        self.assertIsNone(parse_offset_text("blah"))

    def test_normalize_offsets(self) -> None:
        self.assertEqual(normalize_offsets(None, has_due=False), [])
        self.assertEqual(normalize_offsets([], has_due=True), [10])
        self.assertEqual(normalize_offsets([10, 10, 60], has_due=True), [10, 60])
        self.assertEqual(
            normalize_offsets([1, 2, 3, 4, 5, 6], has_due=True),
            [1, 2, 3, 4, 5],
        )

    def test_iso_roundtrip(self) -> None:
        dt = datetime(2026, 8, 17, 18, 0, tzinfo=TZ)
        back = from_iso(to_iso(dt), TZ)
        self.assertEqual(back.astimezone(TZ).replace(tzinfo=TZ), dt)

    def test_next_weekly(self) -> None:
        # Monday 10:00; ask for Wednesday 09:00 → this week Wed
        now = datetime(2026, 8, 17, 10, 0, tzinfo=TZ)  # Monday
        nxt = next_weekly_occurrence(2, "09:00", TZ, now=now)
        self.assertEqual(nxt.weekday(), 2)
        self.assertEqual(nxt.day, 19)

        # Wednesday 10:00; Wednesday 09:00 already passed → next week
        now2 = datetime(2026, 8, 19, 10, 0, tzinfo=TZ)
        nxt2 = next_weekly_occurrence(2, "09:00", TZ, now=now2)
        self.assertEqual(nxt2.day, 26)


class DbTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "test.db")
        await self.db.connect()

    async def asyncTearDown(self) -> None:
        await self.db.close()
        self.tmp.cleanup()

    async def test_admin_bootstrap_and_roles(self) -> None:
        u1, created1 = await self.db.upsert_user(100, "a", "Parent Candidate")
        self.assertTrue(created1)
        self.assertTrue(u1.is_admin)
        self.assertEqual(u1.role, "child")

        u2, created2 = await self.db.upsert_user(200, "b", "Kid")
        self.assertTrue(created2)
        self.assertFalse(u2.is_admin)

        u1b, created_again = await self.db.upsert_user(100, "a2", "Parent Candidate")
        self.assertFalse(created_again)
        self.assertTrue(u1b.is_admin)

        parent = await self.db.set_role(100, "parent")
        assert parent is not None
        self.assertTrue(parent.is_parent)

        await self.db.set_admin(200, True)
        self.assertEqual(await self.db.count_admins(), 2)
        await self.db.set_admin(200, False)
        self.assertEqual(await self.db.count_admins(), 1)

    async def test_task_crud_and_permissions(self) -> None:
        parent, _ = await self.db.upsert_user(1, "p", "P")
        await self.db.set_role(1, "parent")
        child, _ = await self.db.upsert_user(2, "c", "C")

        task = await self.db.create_task(
            title="Homework",
            description="math",
            link="https://example.com",
            due_at="2026-08-18T15:00:00Z",
            created_by=child.telegram_id,
            assigned_to=child.telegram_id,
            offsets=[10, 60],
        )
        offs = await self.db.get_offsets("task", task.id)
        self.assertEqual([o.before_minutes for o in offs], [60, 10])

        self.assertEqual(task.assigned_to, child.telegram_id)
        self.assertTrue(can_edit_task(child, task.created_by))
        parent_user = await self.db.get_user(1)
        assert parent_user is not None
        self.assertTrue(can_edit_task(parent_user, task.created_by))

        other, _ = await self.db.upsert_user(3, "o", "Other child")
        self.assertFalse(can_edit_task(other, task.created_by))

        done = await self.db.set_task_status(task.id, "done", child.telegram_id)
        assert done is not None
        self.assertEqual(done.status, "done")
        open_tasks = await self.db.list_tasks(status="open")
        self.assertEqual(open_tasks, [])

        await self.db.set_offsets("task", task.id, [0, 30])
        offs2 = await self.db.get_offsets("task", task.id)
        self.assertEqual([o.before_minutes for o in offs2], [30, 0])

        await self.db.delete_task(task.id)
        self.assertIsNone(await self.db.get_task(task.id))
        self.assertEqual(await self.db.get_offsets("task", task.id), [])

    async def test_schedule_weekly_and_once(self) -> None:
        user, _ = await self.db.upsert_user(9, "u", "U")
        weekly = await self.db.create_schedule(
            kind="weekly",
            title="Басейн",
            description=None,
            link=None,
            weekday=2,
            start_time="17:00",
            end_time="18:00",
            starts_at=None,
            ends_at=None,
            created_by=user.telegram_id,
            offsets=[10],
        )
        once = await self.db.create_schedule(
            kind="once",
            title="Концерт",
            description="hall",
            link=None,
            weekday=None,
            start_time=None,
            end_time=None,
            starts_at="2026-08-20T18:00:00Z",
            ends_at=None,
            created_by=user.telegram_id,
            offsets=[60, 1440],
        )
        items = await self.db.list_schedule()
        self.assertEqual(len(items), 2)
        self.assertEqual(weekly.kind, "weekly")
        self.assertEqual(once.kind, "once")
        self.assertEqual(len(await self.db.get_offsets("schedule", once.id)), 2)

        await self.db.delete_schedule(weekly.id)
        self.assertIsNone(await self.db.get_schedule(weekly.id))

    async def test_settings_digest(self) -> None:
        self.assertEqual(await self.db.get_setting("digest_time"), "20:00")
        await self.db.set_setting("digest_time", "21:30")
        self.assertEqual(await self.db.get_setting("digest_time"), "21:30")

    async def test_mark_offset_sent(self) -> None:
        user, _ = await self.db.upsert_user(5, "x", "X")
        task = await self.db.create_task(
            title="T",
            description=None,
            link=None,
            due_at="2026-08-18T15:00:00Z",
            created_by=user.telegram_id,
            assigned_to=user.telegram_id,
            offsets=[10],
        )
        off = (await self.db.get_offsets("task", task.id))[0]
        await self.db.mark_offset_sent(off.id, "2026-08-18T15:00:00Z")
        off2 = (await self.db.get_offsets("task", task.id))[0]
        self.assertEqual(off2.last_sent_occurrence, "2026-08-18T15:00:00Z")


class ReminderLogicTests(unittest.TestCase):
    def test_remind_at_math(self) -> None:
        due = datetime(2026, 8, 18, 15, 0, tzinfo=TZ)
        remind = due - timedelta(minutes=10)
        self.assertEqual(remind.hour, 14)
        self.assertEqual(remind.minute, 50)

    def test_schedule_week_filters_past_items(self) -> None:
        now = datetime(2026, 8, 18, 10, 0, tzinfo=TZ)
        start, end = schedule_handlers._week_bounds(TZ, now)

        past_once = ScheduleItem(
            id=1,
            kind="once",
            title="Past",
            description=None,
            link=None,
            weekday=None,
            start_time=None,
            end_time=None,
            starts_at="2026-08-17T07:00:00Z",
            ends_at=None,
            created_by=1,
            created_at="2026-08-17T06:00:00Z",
        )
        future_once = ScheduleItem(
            id=2,
            kind="once",
            title="Future",
            description=None,
            link=None,
            weekday=None,
            start_time=None,
            end_time=None,
            starts_at="2026-08-19T07:00:00Z",
            ends_at=None,
            created_by=1,
            created_at="2026-08-17T06:00:00Z",
        )
        past_weekly = ScheduleItem(
            id=3,
            kind="weekly",
            title="Morning",
            description=None,
            link=None,
            weekday=1,
            start_time="09:00",
            end_time=None,
            starts_at=None,
            ends_at=None,
            created_by=1,
            created_at="2026-08-17T06:00:00Z",
        )

        self.assertFalse(schedule_handlers._item_in_week(past_once, start, end, TZ))
        self.assertTrue(schedule_handlers._item_in_week(future_once, start, end, TZ))
        self.assertFalse(schedule_handlers._item_on_day(past_weekly, now, TZ))


class LlmTests(unittest.TestCase):
    def test_trim_history(self) -> None:
        history = [{"role": "user", "content": f"m{i}"} for i in range(20)]
        trimmed = trim_history(history, limit=16)
        self.assertEqual(len(trimmed), 16)
        self.assertEqual(trimmed[0]["content"], "m4")
        self.assertEqual(trimmed[-1]["content"], "m19")

    def test_append_turn(self) -> None:
        history = [{"role": "user", "content": "hi"}]
        updated = append_turn(history, "next", "reply", limit=4)
        self.assertEqual(len(updated), 3)
        self.assertEqual(updated[-1]["content"], "reply")

    def test_truncate_response(self) -> None:
        self.assertEqual(truncate_response("  hello  "), "hello")
        long_text = "x" * 4000
        self.assertTrue(truncate_response(long_text).endswith("…"))
        self.assertLessEqual(len(truncate_response(long_text)), 3500)

    def test_parse_chat_response(self) -> None:
        payload = {"message": {"role": "assistant", "content": "  Хе-хе!  "}}
        self.assertEqual(parse_chat_response(payload), "Хе-хе!")

    def test_parse_chat_response_errors(self) -> None:
        with self.assertRaises(OllamaError):
            parse_chat_response({})
        with self.assertRaises(OllamaError):
            parse_chat_response({"message": {"content": "   "}})


class OllamaClientTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.client = OllamaClient("http://localhost:11434", "qwen2.5:3b", 30.0)
        await self.client.open()

    async def asyncTearDown(self) -> None:
        await self.client.close()

    async def test_chat_success(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"role": "assistant", "content": "Привіт! 💜"},
        }
        with patch.object(
            self.client.client,
            "post",
            new=AsyncMock(return_value=mock_response),
        ) as post_mock:
            reply = await self.client.chat([{"role": "user", "content": "hi"}])
        self.assertEqual(reply, "Привіт! 💜")
        post_mock.assert_awaited_once()
        body = post_mock.await_args.kwargs["json"]
        self.assertFalse(body["stream"])
        self.assertEqual(body["model"], "qwen2.5:3b")

    async def test_chat_http_error(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "model not found"
        with patch.object(
            self.client.client,
            "post",
            new=AsyncMock(return_value=mock_response),
        ):
            with self.assertRaises(OllamaModelError):
                await self.client.chat([{"role": "user", "content": "hi"}])

    async def test_chat_timeout(self) -> None:
        import httpx

        with patch.object(
            self.client.client,
            "post",
            new=AsyncMock(side_effect=httpx.TimeoutException("timeout")),
        ):
            with self.assertRaises(OllamaTimeoutError):
                await self.client.chat([{"role": "user", "content": "hi"}])

    async def test_chat_unavailable(self) -> None:
        import httpx

        with patch.object(
            self.client.client,
            "post",
            new=AsyncMock(side_effect=httpx.ConnectError("refused")),
        ):
            with self.assertRaises(OllamaUnavailableError):
                await self.client.chat([{"role": "user", "content": "hi"}])


class ImportSmokeTests(unittest.TestCase):
    def test_import_app(self) -> None:
        from bot.handlers import admin, chat, menu, reminders, schedule, start, tasks
        from bot.main import main
        from bot.reminders import ReminderService
        from bot.stickers import StickerService

        self.assertTrue(callable(main))
        self.assertTrue(start.router)
        self.assertTrue(menu.router)
        self.assertTrue(tasks.router)
        self.assertTrue(schedule.router)
        self.assertTrue(reminders.router)
        self.assertTrue(admin.router)
        self.assertTrue(chat.router)
        self.assertTrue(ReminderService)
        self.assertTrue(StickerService)


if __name__ == "__main__":
    unittest.main()
