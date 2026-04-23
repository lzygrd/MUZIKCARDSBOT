from __future__ import annotations

import time

from app.context import AppContext
from app.handlers.common import ensure_player, safe_send_card_media
from app.services.game_logic import random_card, xp_for_rarity
from app.utils.formatters import format_cooldown


def _collect_card(ctx: AppContext, chat_id: int, user) -> None:
    ensure_player(ctx, user)
    user_id = user.id
    now = time.time()

    user_row = ctx.db.get_user(user_id)
    delta = now - float(user_row['last_collect'])
    if delta < ctx.settings.collect_cooldown_seconds:
        remaining = int(ctx.settings.collect_cooldown_seconds - delta)
        ctx.bot.send_message(chat_id, f'⏳ Подожди {format_cooldown(remaining)}!')
        return

    card = random_card()
    xp = xp_for_rarity(card['rarity'])
    duplicate_count = ctx.db.count_card_duplicates(user_id, card['artist'], card['name'])
    duplicate_bonus = 10 if duplicate_count else 0
    ctx.db.add_card(user_id, card['name'], card['artist'], card['rarity'], acquired_from='collect')
    ctx.db.add_xp(user_id, xp + duplicate_bonus)
    ctx.db.set_last_collect(user_id, now)
    ctx.db.log_event(user_id, 'collect_card', {'rarity': card['rarity'], 'bonus_xp': duplicate_bonus})
    extra = f'⚡ +{xp} XP'
    if duplicate_bonus:
        extra += f'\n♻️ Дубликат-бонус: +{duplicate_bonus} XP'
    text = (
        '🎉 Тебе выпала карта!\n\n'
        f'🎤 <b>{card["artist"]}</b>\n'
        f'💿 {card["name"]}\n'
        f'✨ Редкость: {card["rarity"]}\n'
        f'{extra}'
    )
    safe_send_card_media(ctx, chat_id, text, card['artist'], card['name'])



def register_collect_handlers(ctx: AppContext) -> None:
    bot = ctx.bot

    @bot.message_handler(func=lambda m: m.text == '🎴 Получить карту')
    def collect_card(message):
        _collect_card(ctx, message.chat.id, message.from_user)
