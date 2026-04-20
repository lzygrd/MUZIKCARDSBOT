from __future__ import annotations

import random
import time

from app.context import AppContext
from app.handlers.common import antispam_callback, antispam_message, edit_or_send_text, ensure_player, safe_send_card_media
from app.keyboards import build_inline_menu
from app.services.game_logic import daily_xp_reward, random_card
from app.utils.formatters import format_cooldown


def _daily_reward(ctx: AppContext, target, user) -> None:
    ensure_player(ctx, user)
    user_id = user.id
    user_row = ctx.db.get_user(user_id)
    now = time.time()
    delta = now - float(user_row['last_daily'])
    cooldown = ctx.settings.daily_reward_cooldown_seconds
    if delta < cooldown:
        remaining = int(cooldown - delta)
        edit_or_send_text(ctx, target, f'⏳ Награда доступна через {format_cooldown(remaining)}', build_inline_menu())
        return

    old_streak = int(user_row['daily_streak'])
    streak = old_streak + 1 if delta <= cooldown * 2 and float(user_row['last_daily']) > 0 else 1
    ctx.db.set_daily_state(user_id, now, streak)

    if random.choice([True, False]):
        xp = daily_xp_reward(streak)
        ctx.db.add_xp(user_id, xp)
        ctx.db.log_event(user_id, 'daily_xp', {'xp': xp, 'streak': streak})
        edit_or_send_text(ctx, target, f'🎉 Ты получил {xp} XP!\n🔥 Серия входов: {streak}', build_inline_menu())
        return

    card = random_card()
    ctx.db.add_card(user_id, card['name'], card['artist'], card['rarity'], acquired_from='daily')
    ctx.db.log_event(user_id, 'daily_card', {'rarity': card['rarity'], 'streak': streak})
    text = (
        '🎉 Ежедневная награда активирована!\n\n'
        f'🎤 <b>{card["artist"]}</b>\n'
        f'💿 {card["name"]}\n'
        f'✨ Редкость: {card["rarity"]}\n'
        f'🔥 Серия входов: {streak}'
    )
    if hasattr(target, 'message_id'):
        safe_send_card_media(ctx, target.chat.id, text, card['artist'], card['name'], build_inline_menu())
    else:
        safe_send_card_media(ctx, target.chat.id, text, card['artist'], card['name'], build_inline_menu())



def register_reward_handlers(ctx: AppContext) -> None:
    bot = ctx.bot

    @bot.message_handler(func=lambda m: m.text == '🎁 Ежедневная награда')
    @bot.message_handler(commands=['daily'])
    def daily_reward(message):
        if not antispam_message(ctx, message, 'daily', limit=2, window_seconds=3):
            return
        _daily_reward(ctx, message, message.from_user)

    @bot.callback_query_handler(func=lambda c: c.data == 'menu_daily')
    def daily_reward_from_menu(call):
        if not antispam_callback(ctx, call, 'menu_daily', limit=2, window_seconds=3):
            return
        _daily_reward(ctx, call.message, call.from_user)
        bot.answer_callback_query(call.id)
