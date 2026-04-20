from __future__ import annotations

from telebot import types

from app.context import AppContext
from app.data import RARITY_ALIASES
from app.handlers.common import antispam_callback, antispam_message, edit_or_send_text, ensure_player, safe_send_card_media
from app.keyboards import build_collection_keyboard, build_inline_menu
from app.utils.formatters import format_card_text


def _build_nav_keyboard(index: int, total: int, rarity: str) -> types.InlineKeyboardMarkup:
    keyboard = types.InlineKeyboardMarkup()
    rarity_safe = rarity.replace(' ', '_')
    row = []
    if index > 0:
        row.append(types.InlineKeyboardButton('⬅️ Назад', callback_data=f'prev_{index}_{rarity_safe}'))
    if index < total - 1:
        row.append(types.InlineKeyboardButton('➡️ Вперёд', callback_data=f'next_{index}_{rarity_safe}'))
    if row:
        keyboard.row(*row)
    keyboard.add(types.InlineKeyboardButton('⬅️ К выбору редкости', callback_data='collection_back'))
    keyboard.add(types.InlineKeyboardButton('📋 В меню', callback_data='menu_back'))
    return keyboard



def _collection_text(ctx: AppContext, user_id: int) -> str:
    rarity_counts = ctx.db.get_rarity_counts(user_id)
    return '\n'.join([
        '📚 <b>Твоя коллекция</b>',
        '',
        f'🎴 Single: {rarity_counts.get("single", 0)}',
        f'💿 Album: {rarity_counts.get("album", 0)}',
        f'✨ Limited: {rarity_counts.get("limited edition", 0)}',
        '',
        'Выбери коллекцию:',
    ])



def _show_collection_menu(ctx: AppContext, target, user) -> None:
    ensure_player(ctx, user)
    user_id = user.id
    count = ctx.db.get_user_cards_count(user_id)
    if count == 0:
        edit_or_send_text(ctx, target, '📭 У тебя пока нет карт!', build_inline_menu())
        return
    edit_or_send_text(ctx, target, _collection_text(ctx, user_id), build_collection_keyboard(prefix='show'))



def register_collection_handlers(ctx: AppContext) -> None:
    bot = ctx.bot

    @bot.message_handler(func=lambda m: m.text == '📚 Мои карты')
    def my_cards(message):
        if not antispam_message(ctx, message, 'collection'):
            return
        _show_collection_menu(ctx, message, message.from_user)

    @bot.callback_query_handler(func=lambda c: c.data == 'menu_collection')
    def my_cards_from_menu(call):
        if not antispam_callback(ctx, call, 'menu_collection'):
            return
        _show_collection_menu(ctx, call.message, call.from_user)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == 'collection_back')
    def collection_back(call):
        if not antispam_callback(ctx, call, 'collection_back'):
            return
        _show_collection_menu(ctx, call.message, call.from_user)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith('show_'))
    def show_collection(call):
        if not antispam_callback(ctx, call, 'show_collection', limit=8, window_seconds=3):
            return
        rarity_key = call.data.split('_', maxsplit=1)[1]
        rarity = RARITY_ALIASES.get(rarity_key, 'single')
        cards_list = ctx.db.get_user_cards_by_rarity(call.from_user.id, rarity)
        if not cards_list:
            bot.answer_callback_query(call.id, '📭 У тебя нет карт этой редкости!')
            return
        card = cards_list[0]
        text = format_card_text(card['id'], card['artist'], card['name'], card['rarity'], index=0, total=len(cards_list))
        keyboard = _build_nav_keyboard(0, len(cards_list), rarity)
        safe_send_card_media(ctx, call.message.chat.id, text, card['artist'], card['name'], keyboard)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith(('next_', 'prev_')))
    def navigate_card(call):
        if not antispam_callback(ctx, call, 'navigate_card', limit=10, window_seconds=3):
            return

        try:
            direction, current_index_raw, rarity_raw = call.data.split('_', maxsplit=2)
            current_index = int(current_index_raw)
            rarity = rarity_raw.replace('_', ' ')

            cards_list = ctx.db.get_user_cards_by_rarity(call.from_user.id, rarity)
            if not cards_list:
                bot.answer_callback_query(call.id, '📭 У тебя нет карт этой редкости!')
                return

            new_index = min(current_index + 1, len(cards_list) - 1) if direction == 'next' else max(current_index - 1,
                                                                                                    0)
            card = cards_list[new_index]

            text = format_card_text(
                card['id'],
                card['artist'],
                card['name'],
                card['rarity'],
                index=new_index,
                total=len(cards_list)
            )

            keyboard = _build_nav_keyboard(new_index, len(cards_list), rarity)

            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except Exception:
                pass

            safe_send_card_media(
                ctx,
                call.message.chat.id,
                text,
                card['artist'],
                card['name'],
                keyboard
            )

            bot.answer_callback_query(call.id)

        except Exception as e:
            print(f'navigate_card error: {e}')
            bot.answer_callback_query(call.id, '❌ Не получилось показать карту.')