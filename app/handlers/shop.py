from __future__ import annotations

from app.context import AppContext
from app.handlers.common import antispam_callback, antispam_message, edit_or_send_text, ensure_player, safe_send_card_media
from app.keyboards import build_shop_keyboard
from app.services.game_logic import build_pack, random_card, summarise_rarities


def _open_shop(ctx: AppContext, target, user) -> None:
    ensure_player(ctx, user)
    edit_or_send_text(ctx, target, '🛒 <b>Магазин</b>\nВыбери действие:', build_shop_keyboard())



def register_shop_handlers(ctx: AppContext) -> None:
    bot = ctx.bot

    @bot.message_handler(func=lambda m: m.text == '🛒 Магазин')
    def shop(message):
        if not antispam_message(ctx, message, 'shop'):
            return
        _open_shop(ctx, message, message.from_user)

    @bot.callback_query_handler(func=lambda c: c.data == 'menu_shop')
    def shop_from_menu(call):
        if not antispam_callback(ctx, call, 'menu_shop'):
            return
        _open_shop(ctx, call.message, call.from_user)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith('shop_'))
    def shop_actions(call):
        if not antispam_callback(ctx, call, 'shop_actions', limit=5, window_seconds=3):
            return
        ensure_player(ctx, call.from_user)
        user_id = call.from_user.id

        if call.data == 'shop_buy_card':
            cost = ctx.settings.buy_random_card_cost
            if not ctx.db.spend_xp(user_id, cost):
                bot.answer_callback_query(call.id, f'❌ Недостаточно XP! Нужно {cost} XP')
                return
            card = random_card()
            ctx.db.add_card(user_id, card['name'], card['artist'], card['rarity'], acquired_from='shop_random')
            ctx.db.log_event(user_id, 'shop_buy_card', {'cost': cost, 'rarity': card['rarity']})
            text = (
                '✅ Ты купил карту!\n'
                f'🎤 <b>{card["artist"]}</b>\n'
                f'💿 {card["name"]}\n'
                f'✨ Редкость: {card["rarity"]}\n'
                f'💰 -{cost} XP'
            )
            safe_send_card_media(ctx, call.message.chat.id, text, card['artist'], card['name'], build_shop_keyboard())
            bot.answer_callback_query(call.id, 'Покупка прошла успешно!')
            return

        if call.data == 'shop_remove_cooldown':
            cost = ctx.settings.reset_cooldown_cost
            if not ctx.db.spend_xp(user_id, cost):
                bot.answer_callback_query(call.id, f'❌ Недостаточно XP! Нужно {cost} XP')
                return
            ctx.db.set_last_collect(user_id, 0)
            ctx.db.log_event(user_id, 'shop_reset_cooldown', {'cost': cost})
            edit_or_send_text(ctx, call.message, f'✅ Кулдаун сброшен!\n💰 -{cost} XP', build_shop_keyboard())
            bot.answer_callback_query(call.id, f'✅ Кулдаун сброшен! -{cost} XP')
            return

        if call.data in {'shop_pack_basic', 'shop_pack_premium'}:
            pack_key = 'basic' if call.data.endswith('basic') else 'premium'
            cost = ctx.settings.basic_pack_cost if pack_key == 'basic' else ctx.settings.premium_pack_cost
            if not ctx.db.spend_xp(user_id, cost):
                bot.answer_callback_query(call.id, f'❌ Недостаточно XP! Нужно {cost} XP')
                return
            cards = build_pack(pack_key)
            for card in cards:
                ctx.db.add_card(user_id, card['name'], card['artist'], card['rarity'], acquired_from=f'pack_{pack_key}')

            ctx.db.log_event(user_id, 'shop_pack_open', {'pack': pack_key, 'cost': cost, 'rarities': summarise_rarities(cards)})
            lines = [
                f'📦 <b>{pack_key.title()} Pack открыт!</b>',
                f'💰 -{cost} XP',
                '',
            ]
            for idx, card in enumerate(cards, start=1):
                lines.append(f'{idx}. {card["rarity"]} — <b>{card["artist"]}</b> / {card["name"]}')
            edit_or_send_text(ctx, call.message, '\n'.join(lines), build_shop_keyboard())
            bot.answer_callback_query(call.id, 'Пак открыт!')
            return
