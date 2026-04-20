from __future__ import annotations

from dataclasses import dataclass, field

import telebot

from app.config import Settings
from app.db import Database
from app.services.antispam import AntiSpamService


@dataclass(slots=True)
class AppContext:
    bot: telebot.TeleBot
    settings: Settings
    db: Database
    antispam: AntiSpamService = field(default_factory=AntiSpamService)
