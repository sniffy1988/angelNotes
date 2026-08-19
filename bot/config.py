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
DEFAULT_OLLAMA_URL = "http://host.docker.internal:11434"
DEFAULT_OLLAMA_MODEL = "qwen2.5:3b"
DEFAULT_OLLAMA_TIMEOUT = 120.0


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    tz_name: str
    sticker_set: str
    db_path: Path
    ollama_url: str
    ollama_model: str
    ollama_timeout: float

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.tz_name)


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name, str(default)).strip()
    try:
        return float(raw)
    except ValueError:
        return default


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
        ollama_url=os.getenv("OLLAMA_URL", DEFAULT_OLLAMA_URL).strip()
        or DEFAULT_OLLAMA_URL,
        ollama_model=os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL).strip()
        or DEFAULT_OLLAMA_MODEL,
        ollama_timeout=_float_env("OLLAMA_TIMEOUT", DEFAULT_OLLAMA_TIMEOUT),
    )
