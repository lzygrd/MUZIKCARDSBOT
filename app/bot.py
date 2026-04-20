from __future__ import annotations

import logging
import time

import requests
import telebot

from app.config import get_settings
from app.context import AppContext
from app.db import Database
from app.handlers.collection import register_collection_handlers
from app.handlers.collect import register_collect_handlers
from app.handlers.common import register_common_handlers
from app.handlers.profile import register_profile_handlers
from app.handlers.rewards import register_reward_handlers
from app.handlers.roulette import register_roulette_handlers
from app.handlers.shop import register_shop_handlers
from app.handlers.social import register_social_handlers
from app.handlers.trade import register_trade_handlers


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    )


def build_app() -> AppContext:
    settings = get_settings()
    configure_logging(settings.log_level)
    bot = telebot.TeleBot(settings.bot_token, threaded=True, parse_mode='HTML')
    db = Database(settings.db_path)
    ctx = AppContext(bot=bot, settings=settings, db=db)
    register_common_handlers(ctx)
    register_profile_handlers(ctx)
    register_reward_handlers(ctx)
    register_collection_handlers(ctx)
    register_collect_handlers(ctx)
    register_shop_handlers(ctx)
    register_trade_handlers(ctx)
    register_social_handlers(ctx)
    register_roulette_handlers(ctx)
    return ctx


def run() -> None:
    ctx = build_app()
    logger = logging.getLogger(__name__)
    logger.info('🚀 MUZCARD PRO запущен')
    while True:
        try:
            ctx.bot.infinity_polling(
                timeout=ctx.settings.poll_timeout,
                long_polling_timeout=ctx.settings.long_polling_timeout,
                skip_pending=True,
                allowed_updates=['message', 'callback_query'],
            )
        except requests.exceptions.ReadTimeout:
            logger.warning('Timeout. Переподключаю polling...')
            time.sleep(3)
        except requests.exceptions.ConnectionError:
            logger.warning('Нет соединения. Переподключаю polling...')
            time.sleep(3)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            logger.exception('Неожиданная ошибка polling: %s', exc)
            time.sleep(5)
