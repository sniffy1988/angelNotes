from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT_DIR / "data" / "bot.db"
DEFAULT_STICKER_SET = "kuuuuurrrrooommmiii_by_e4zybot"
DEFAULT_TZ = "Europe/Kyiv"
DEFAULT_DIGEST_TIME = "20:00"
MAX_REMINDER_OFFSETS = 5
DEFAULT_REMIND_BEFORE = 10


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    tz_name: str
    sticker_set: str
    db_path: Path

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.tz_name)


def load_settings() -> Settings:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is required in .env")

    db_raw = os.getenv("DB_PATH", str(DEFAULT_DB)).strip()
    db_path = Path(db_raw)
    if not db_path.is_absolute():
        db_path = ROOT_DIR / db_path

    return Settings(
        bot_token=token,
        tz_name=os.getenv("TZ", DEFAULT_TZ).strip() or DEFAULT_TZ,
        sticker_set=os.getenv("STICKER_SET", DEFAULT_STICKER_SET).strip()
        or DEFAULT_STICKER_SET,
        db_path=db_path,
    )
