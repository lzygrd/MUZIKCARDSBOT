from __future__ import annotations

import time

from app.context import AppContext
from app.handlers.common import antispam_callback, antispam_message, edit_or_send_text, ensure_player
from app.keyboards import build_inline_menu
from app.utils.formatters import format_profile


def _send_profile(ctx: AppContext, target, user) -> None:
    ensure_player(ctx, user)
    user_id = user.id
    user_row = ctx.db.get_user(user_id)
    total_cards = ctx.db.get_user_cards_count(user_id)
    rarity_counts = ctx.db.get_rarity_counts(user_id)
    now = time.time()
    next_collect_in = max(0, int(ctx.settings.collect_cooldown_seconds - (now - float(user_row['last_collect']))))
    next_daily_in = max(0, int(ctx.settings.daily_reward_cooldown_seconds - (now - float(user_row['last_daily']))))
    battle = ctx.db.get_battle_profile(user_id)
    clan = ctx.db.get_user_clan(user_id)
    deck_size = len(ctx.db.get_deck(user_id))
    text = format_profile(
        dict(user_row),
        total_cards,
        rarity_counts,
        next_collect_in,
        next_daily_in,
        battle=dict(battle),
        clan_name=f'[{clan["tag"]}] {clan["name"]}' if clan else None,
        deck_size=deck_size,
    )
    edit_or_send_text(ctx, target, text, build_inline_menu())



def _send_top(ctx: AppContext, target, user) -> None:
    ensure_player(ctx, user)
    users = ctx.db.get_top_users(limit=10)
    lines = ['🏆 <b>ТОП ИГРОКОВ</b>', '']
    for idx, item in enumerate(users, start=1):
        username = item['username'] or f'User{item["user_id"]}'
        prefix = '@' if not str(username).startswith('User') else ''
        lines.append(f'{idx}. {prefix}{username} — {int(item["xp"])} XP • {int(item["cards_count"])} карт')
    edit_or_send_text(ctx, target, '\n'.join(lines), build_inline_menu())



def register_profile_handlers(ctx: AppContext) -> None:
    bot = ctx.bot

    @bot.message_handler(func=lambda m: m.text == '👤 Профиль')
    def profile(message):
        if not antispam_message(ctx, message, 'profile'):
            return
        _send_profile(ctx, message, message.from_user)

    @bot.message_handler(func=lambda m: m.text == '🏆 Топ')
    def top(message):
        if not antispam_message(ctx, message, 'top'):
            return
        _send_top(ctx, message, message.from_user)

    @bot.callback_query_handler(func=lambda c: c.data == 'menu_profile')
    def profile_from_menu(call):
        if not antispam_callback(ctx, call, 'menu_profile'):
            return
        _send_profile(ctx, call.message, call.from_user)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == 'menu_top')
    def top_from_menu(call):
        if not antispam_callback(ctx, call, 'menu_top'):
            return
        _send_top(ctx, call.message, call.from_user)
        bot.answer_callback_query(call.id)
