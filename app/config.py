from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    db_path: Path
    hi_gif_path: Path
    log_level: str = 'INFO'
    collect_cooldown_seconds: int = 0
    daily_reward_cooldown_seconds: int = 0
    starter_xp: int = 0
    buy_random_card_cost: int = 500
    reset_cooldown_cost: int = 250
    basic_pack_cost: int = 900
    premium_pack_cost: int = 1800
    poll_timeout: int = 30
    long_polling_timeout: int = 30


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, '').strip()
    return int(raw) if raw else default


def get_settings() -> Settings:
    token = os.getenv('BOT_TOKEN', '').strip()
    if not token:
        raise RuntimeError('BOT_TOKEN не найден. Создай .env из .env.example и вставь новый токен.')

    return Settings(
        bot_token=token,
        db_path=Path(os.getenv('DB_PATH', BASE_DIR / 'data' / 'bot.db')),
        hi_gif_path=Path(os.getenv('HI_GIF_PATH', BASE_DIR / 'assets' / 'hi.gif')),
        log_level=os.getenv('LOG_LEVEL', 'INFO').upper(),
        collect_cooldown_seconds=_env_int('COLLECT_COOLDOWN_SECONDS', 0),
        daily_reward_cooldown_seconds=_env_int('DAILY_REWARD_COOLDOWN_SECONDS', 0),
        starter_xp=_env_int('STARTER_XP', 0),
        buy_random_card_cost=_env_int('BUY_RANDOM_CARD_COST', 500),
        reset_cooldown_cost=_env_int('RESET_COOLDOWN_COST', 250),
        basic_pack_cost=_env_int('BASIC_PACK_COST', 900),
        premium_pack_cost=_env_int('PREMIUM_PACK_COST', 1800),
        poll_timeout=_env_int('POLL_TIMEOUT', 30),
        long_polling_timeout=_env_int('LONG_POLLING_TIMEOUT', 30),
    )
