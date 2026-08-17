from __future__ import annotations

import logging
import random
from typing import Literal

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

Mood = Literal[
    "start",
    "saved",
    "done",
    "remind",
    "digest",
    "deny",
    "error",
    "empty",
]

# Indices in kuuuuurrrrooommmiii_by_e4zybot after removing promo sticker (@emojipipka).
# Source: https://stickers.wiki/ru/telegram/kuuuuurrrrooommmiii_by_e4zybot/
MOOD_INDICES: dict[Mood, list[int]] = {
    "start": [13],  # Hey!
    "saved": [0, 1],  # Thanks, OK
    "done": [2, 12],  # Nice work!, GREAT!
    "remind": [13, 10, 19],  # Hey!, Huh?, He he...
    "digest": [9],  # zzz
    "deny": [11],  # Don't be silly!
    "error": [14, 4],  # What?!, Please?
    "empty": [10],  # Huh?
}

PROMO_INDEX = 8  # «Більше @emojipipka»

logger = logging.getLogger(__name__)


class StickerService:
    def __init__(self, set_name: str) -> None:
        self.set_name = set_name
        self._file_ids: list[str] = []
        self._ready = False

    async def load(self, bot: Bot) -> None:
        try:
            sticker_set = await bot.get_sticker_set(self.set_name)
        except TelegramAPIError as exc:
            logger.warning("Cannot load sticker set %s: %s", self.set_name, exc)
            self._ready = False
            return

        ids: list[str] = []
        for i, sticker in enumerate(sticker_set.stickers):
            if i == PROMO_INDEX:
                continue
            if sticker.file_id:
                ids.append(sticker.file_id)

        # If pack length differs, keep all non-empty and still allow index map with clamp
        if not ids and sticker_set.stickers:
            ids = [s.file_id for s in sticker_set.stickers if s.file_id]

        self._file_ids = ids
        self._ready = bool(ids)
        logger.info("Loaded sticker set %s: %s stickers", self.set_name, len(ids))

    def _pick_for_mood(self, mood: Mood) -> str | None:
        if not self._ready:
            return None
        indices = MOOD_INDICES.get(mood, [])
        # Map original pack indices (with promo) to filtered list indices
        candidates: list[str] = []
        for original_idx in indices:
            filtered_idx = original_idx if original_idx < PROMO_INDEX else original_idx - 1
            if 0 <= filtered_idx < len(self._file_ids):
                candidates.append(self._file_ids[filtered_idx])
        if not candidates:
            return self._file_ids[hash(mood) % len(self._file_ids)]
        return random.choice(candidates)

    async def send_mood(self, bot: Bot, chat_id: int, mood: Mood) -> bool:
        file_id = self._pick_for_mood(mood)
        if not file_id:
            return False
        try:
            await bot.send_sticker(chat_id, file_id)
            return True
        except TelegramAPIError as exc:
            logger.warning("Failed to send sticker: %s", exc)
            return False
