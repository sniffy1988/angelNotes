from __future__ import annotations

import logging
from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from bot import texts
from bot.config import DEFAULT_DIGEST_TIME, Settings
from bot.db import Database, ScheduleItem, Task
from bot.stickers import StickerService
from bot.utils import (
    escape_html,
    format_dt,
    from_iso,
    next_weekly_occurrence,
    to_iso,
)

logger = logging.getLogger(__name__)


class ReminderService:
    def __init__(
        self,
        bot: Bot,
        db: Database,
        settings: Settings,
        stickers: StickerService,
    ) -> None:
        self.bot = bot
        self.db = db
        self.settings = settings
        self.stickers = stickers
        self.scheduler = AsyncIOScheduler(timezone=settings.tz)

    def start(self) -> None:
        self.scheduler.add_job(
            self.check_offsets,
            IntervalTrigger(minutes=1),
            id="offsets",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        self.scheduler.add_job(
            self.send_digest,
            CronTrigger(minute="*/5", timezone=self.settings.tz),
            id="digest_tick",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        self.scheduler.start()
        logger.info("Reminder scheduler started (%s)", self.settings.tz_name)

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    async def _broadcast(self, text: str, mood: str = "remind") -> None:
        users = await self.db.list_users()
        for user in users:
            try:
                await self.stickers.send_mood(self.bot, user.telegram_id, mood)  # type: ignore[arg-type]
                await self.bot.send_message(
                    user.telegram_id,
                    text,
                    disable_web_page_preview=True,
                )
            except TelegramAPIError as exc:
                logger.warning("Broadcast to %s failed: %s", user.telegram_id, exc)

    def _occurrence_for_task(self, task: Task) -> datetime | None:
        if not task.due_at or task.status != "open":
            return None
        return from_iso(task.due_at, self.settings.tz)

    def _occurrence_for_schedule(
        self, item: ScheduleItem, now: datetime
    ) -> datetime | None:
        if item.kind == "once":
            if not item.starts_at:
                return None
            return from_iso(item.starts_at, self.settings.tz)

        if item.weekday is None or not item.start_time:
            return None

        h, m = map(int, item.start_time.split(":"))
        # Prefer today's occurrence if weekday matches
        if now.weekday() == item.weekday:
            today = now.replace(hour=h, minute=m, second=0, microsecond=0)
            return today
        # Else next upcoming
        return next_weekly_occurrence(
            item.weekday, item.start_time, self.settings.tz, now
        )

    async def check_offsets(self) -> None:
        now = datetime.now(self.settings.tz)
        offsets = await self.db.list_all_offsets()
        for offset in offsets:
            try:
                await self._process_offset(offset, now)
            except Exception:
                logger.exception("Offset %s failed", offset.id)

    async def _process_offset(self, offset, now: datetime) -> None:
        if offset.target_type == "task":
            task = await self.db.get_task(offset.target_id)
            if not task or task.status != "open":
                return
            occurrence = self._occurrence_for_task(task)
            title = task.title
            extra_parts: list[str] = []
            if task.description:
                extra_parts.append(escape_html(task.description))
            if task.link:
                extra_parts.append(f'<a href="{escape_html(task.link)}">посилання</a>')
            if task.due_at:
                extra_parts.append(f"Строк: {format_dt(occurrence, self.settings.tz)}")
            extra = "\n".join(extra_parts)
            once = True
        else:
            item = await self.db.get_schedule(offset.target_id)
            if not item:
                return
            occurrence = self._occurrence_for_schedule(item, now)
            title = item.title
            extra_parts = []
            if item.description:
                extra_parts.append(escape_html(item.description))
            if item.link:
                extra_parts.append(f'<a href="{escape_html(item.link)}">посилання</a>')
            if occurrence:
                extra_parts.append(f"Коли: {format_dt(occurrence, self.settings.tz)}")
            extra = "\n".join(extra_parts)
            once = item.kind == "once"

        if occurrence is None:
            return

        remind_at = occurrence - timedelta(minutes=offset.before_minutes)
        if now < remind_at:
            return

        occ_iso = to_iso(occurrence)
        if offset.last_sent_occurrence == occ_iso:
            return

        # For once events / tasks: also skip if already sent any occurrence
        if once and offset.last_sent_occurrence:
            return

        # Don't spam ancient occurrences (more than 2 hours past remind_at)
        if now - remind_at > timedelta(hours=2):
            await self.db.mark_offset_sent(offset.id, occ_iso)
            return

        if offset.before_minutes == 0:
            when_label = "зараз"
        else:
            when_label = texts.format_offset(offset.before_minutes)

        text = texts.remind_message(escape_html(title), when_label, extra)
        await self._broadcast(text, mood="remind")
        await self.db.mark_offset_sent(offset.id, occ_iso)

    async def send_digest(self) -> None:
        """Tick every 5 minutes; send once when local time matches digest_time."""
        now = datetime.now(self.settings.tz)
        digest_time = (
            await self.db.get_setting("digest_time", DEFAULT_DIGEST_TIME)
            or DEFAULT_DIGEST_TIME
        )
        try:
            hh, mm = map(int, digest_time.split(":"))
        except ValueError:
            hh, mm = 20, 0

        if now.hour != hh or now.minute < mm or now.minute >= mm + 5:
            return

        last = await self.db.get_setting("digest_last_date")
        today = now.date().isoformat()
        if last == today:
            return

        tomorrow = (now + timedelta(days=1)).date()
        lines: list[str] = [texts.digest_header(), ""]

        open_tasks = await self.db.list_tasks(status="open")
        if open_tasks:
            lines.append("<b>Відкриті справи:</b>")
            for t in open_tasks:
                due = f" ({format_dt(from_iso(t.due_at, self.settings.tz), self.settings.tz)})" if t.due_at else ""
                lines.append(f"• {escape_html(t.title)}{due}")
            lines.append("")

        schedule_lines: list[str] = []
        for item in await self.db.list_schedule():
            if item.kind == "weekly" and item.weekday == tomorrow.weekday():
                schedule_lines.append(
                    f"• {escape_html(item.title)} о {item.start_time or '??:??'}"
                )
            elif item.kind == "once" and item.starts_at:
                starts = from_iso(item.starts_at, self.settings.tz)
                if starts.date() == tomorrow:
                    schedule_lines.append(
                        f"• {escape_html(item.title)} о {starts.strftime('%H:%M')}"
                    )

        if schedule_lines:
            lines.append("<b>На завтра:</b>")
            lines.extend(schedule_lines)

        if len(lines) <= 2:
            await self.db.set_setting("digest_last_date", today)
            return

        await self._broadcast("\n".join(lines), mood="digest")
        await self.db.set_setting("digest_last_date", today)
