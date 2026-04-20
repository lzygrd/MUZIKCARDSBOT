from __future__ import annotations

import random
import time

from telebot import types

from app.context import AppContext
from app.data import CARD_POOL
from app.handlers.common import antispam_callback, antispam_message, edit_or_send_text, ensure_player
from app.keyboards import build_inline_menu
from app.services.game_logic import random_card

ROULETTE_SESSIONS: dict[int, dict] = {}


def _update_roulette_menu(ctx: AppContext, message, user_id: int) -> None:
    data = ROULETTE_SESSIONS[user_id]
    selected = data['selected_ids']
    text = f'🎰 <b>Выбери 4 карты</b> ({len(selected)}/4)'
    keyboard = types.InlineKeyboardMarkup()
    for card in data['all_cards']:
        mark = '✅' if card['id'] in selected else '▫️'
        keyboard.add(types.InlineKeyboardButton(f'{mark} [ID:{card["id"]}] {card["artist"]} — {card["name"]}', callback_data=f'pick_{card["id"]}'))
    keyboard.add(types.InlineKeyboardButton('🎲 Поставить', callback_data='roulette_go'))
    keyboard.add(types.InlineKeyboardButton('⬅️ Назад в меню', callback_data='menu_back'))
    try:
        ctx.bot.edit_message_text(text, chat_id=message.chat.id, message_id=message.message_id, reply_markup=keyboard)
    except Exception:
        ctx.bot.send_message(message.chat.id, text, reply_markup=keyboard)



def _roulette_animation(ctx: AppContext, message, target: str) -> None:
    fake_pool = CARD_POOL[target] + CARD_POOL['single']
    for _ in range(6):
        fake = random.choice(fake_pool)
        text = f'🎰 КРУТИМ...\n\n🎤 <b>{fake["artist"]}</b>\n💿 {fake["name"]}'
        try:
            ctx.bot.edit_message_text(text, chat_id=message.chat.id, message_id=message.message_id)
        except Exception:
            pass
        time.sleep(0.3)



def _start_roulette(ctx: AppContext, target, user) -> None:
    ensure_player(ctx, user)
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton('🎴 Single → 💿 Album (50%)', callback_data='roulette_single'))
    keyboard.add(types.InlineKeyboardButton('💿 Album → ✨ Limited (25%)', callback_data='roulette_album'))
    keyboard.add(types.InlineKeyboardButton('⬅️ Назад в меню', callback_data='menu_back'))
    edit_or_send_text(ctx, target, '🎰 Выбери режим:', keyboard)



def register_roulette_handlers(ctx: AppContext) -> None:
    bot = ctx.bot

    @bot.message_handler(func=lambda m: m.text == '🎰 Рулетка')
    def roulette_start(message):
        if not antispam_message(ctx, message, 'roulette'):
            return
        _start_roulette(ctx, message, message.from_user)

    @bot.callback_query_handler(func=lambda c: c.data == 'menu_roulette')
    def roulette_start_from_menu(call):
        if not antispam_callback(ctx, call, 'menu_roulette'):
            return
        _start_roulette(ctx, call.message, call.from_user)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data in {'roulette_single', 'roulette_album'})
    def roulette_play(call):
        if not antispam_callback(ctx, call, 'roulette_play', limit=4, window_seconds=3):
            return
        ensure_player(ctx, call.from_user)
        user_id = call.from_user.id
        if call.data == 'roulette_single':
            need_rarity, target, chance = 'single', 'album', 50
        else:
            need_rarity, target, chance = 'album', 'limited edition', 25

        cards_list = ctx.db.get_user_cards_by_rarity(user_id, need_rarity)
        if len(cards_list) < 4:
            bot.answer_callback_query(call.id, '❌ Нужно минимум 4 карты этой редкости!')
            return

        ROULETTE_SESSIONS[user_id] = {'all_cards': cards_list, 'target': target, 'chance': chance, 'selected_ids': []}
        _update_roulette_menu(ctx, call.message, user_id)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith('pick_'))
    def pick_card(call):
        if not antispam_callback(ctx, call, 'roulette_pick', limit=12, window_seconds=3):
            return
        user_id = call.from_user.id
        session = ROULETTE_SESSIONS.get(user_id)
        if not session:
            bot.answer_callback_query(call.id, '❌ Сессия устарела')
            return
        card_id = int(call.data.split('_')[1])
        selected = session['selected_ids']
        if card_id in selected:
            selected.remove(card_id)
        else:
            if len(selected) >= 4:
                bot.answer_callback_query(call.id, '❌ Максимум 4 карты!')
                return
            selected.append(card_id)
        _update_roulette_menu(ctx, call.message, user_id)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == 'roulette_go')
    def roulette_go(call):
        if not antispam_callback(ctx, call, 'roulette_go', limit=2, window_seconds=4):
            return
        user_id = call.from_user.id
        session = ROULETTE_SESSIONS.get(user_id)
        if not session:
            bot.answer_callback_query(call.id, '❌ Сессия устарела')
            return
        if len(session['selected_ids']) != 4:
            bot.answer_callback_query(call.id, '❌ Выбери 4 карты!')
            return

        ctx.db.delete_user_cards(user_id, session['selected_ids'])
        bot.edit_message_text('🎰 Крутим...', call.message.chat.id, call.message.message_id)
        _roulette_animation(ctx, call.message, session['target'])

        if random.randint(1, 100) <= session['chance']:
            reward = random_card(session['target'])
            ctx.db.add_card(user_id, reward['name'], reward['artist'], reward['rarity'], acquired_from='roulette')
            ctx.db.log_event(user_id, 'roulette_win', {'rarity': reward['rarity']})
            text = f'🎰 СТОП!\n\n🎉 <b>Выигрыш!</b>\n\n🎤 <b>{reward["artist"]}</b>\n💿 {reward["name"]}'
        else:
            ctx.db.log_event(user_id, 'roulette_loss', {'target': session['target']})
            text = '🎰 СТОП!\n\n💀 <b>Проигрыш</b>'

        edit_or_send_text(ctx, call.message, text, build_inline_menu())
        ROULETTE_SESSIONS.pop(user_id, None)
        bot.answer_callback_query(call.id)
