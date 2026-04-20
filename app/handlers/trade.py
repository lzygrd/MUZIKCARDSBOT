from __future__ import annotations

from telebot import types

from app.context import AppContext
from app.data import RARITY_ALIASES
from app.handlers.common import antispam_callback, antispam_message, edit_or_send_text, ensure_player, safe_send_card_media
from app.keyboards import build_social_keyboard
from app.utils.formatters import format_card_text, format_trade_offer

TRADE_PICK_STATE: dict[int, dict] = {}
TRADE_DRAFTS: dict[int, int] = {}


def _send_trade_card(ctx: AppContext, chat_id: int, user_id: int) -> None:
    info = TRADE_PICK_STATE[user_id]
    cards_list = info['cards_list']
    index = info['index']
    card = cards_list[index]
    text = format_card_text(card['id'], card['artist'], card['name'], card['rarity'], index=index, total=len(cards_list), extra='Выбери эту карту для передачи:')
    keyboard = types.InlineKeyboardMarkup()
    row = []
    if index > 0:
        row.append(types.InlineKeyboardButton('⬅️ Назад', callback_data='trade_prev'))
    if index < len(cards_list) - 1:
        row.append(types.InlineKeyboardButton('➡️ Вперёд', callback_data='trade_next'))
    if row:
        keyboard.row(*row)
    keyboard.add(types.InlineKeyboardButton('✅ Выбрать', callback_data=f'trade_select_{card["id"]}'))
    keyboard.add(types.InlineKeyboardButton('⬅️ К выбору редкости', callback_data='trade_back'))
    keyboard.add(types.InlineKeyboardButton('🤝 Социальное', callback_data='menu_social'))
    safe_send_card_media(ctx, chat_id, text, card['artist'], card['name'], keyboard)



def _start_trade(ctx: AppContext, target, user) -> None:
    ensure_player(ctx, user)
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(types.InlineKeyboardButton('🎴 Single', callback_data='trade_collection_single'))
    keyboard.add(types.InlineKeyboardButton('💿 Album', callback_data='trade_collection_album'))
    keyboard.add(types.InlineKeyboardButton('✨ Limited Edition', callback_data='trade_collection_limited'))
    keyboard.add(types.InlineKeyboardButton('⬅️ Назад в социальное', callback_data='menu_social'))
    edit_or_send_text(ctx, target, '🔄 <b>Обмен картой</b>\n\nВыбери редкость карты для обмена:', keyboard)



def register_trade_handlers(ctx: AppContext) -> None:
    bot = ctx.bot

    @bot.message_handler(func=lambda m: m.text == '🔄 Обменять карту')
    def trade_choose_collection(message):
        if not antispam_message(ctx, message, 'trade'):
            return
        _start_trade(ctx, message, message.from_user)

    @bot.callback_query_handler(func=lambda c: c.data == 'menu_trade')
    def trade_from_menu(call):
        if not antispam_callback(ctx, call, 'menu_trade'):
            return
        _start_trade(ctx, call.message, call.from_user)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == 'trade_back')
    def trade_back(call):
        if not antispam_callback(ctx, call, 'trade_back'):
            return
        _start_trade(ctx, call.message, call.from_user)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith('trade_collection_'))
    def trade_show_cards(call):
        if not antispam_callback(ctx, call, 'trade_collection', limit=8, window_seconds=3):
            return
        ensure_player(ctx, call.from_user)
        rarity_key = call.data.split('_', maxsplit=2)[2]
        rarity = RARITY_ALIASES.get(rarity_key, 'single')
        cards_list = ctx.db.get_user_cards_by_rarity(call.from_user.id, rarity)
        if not cards_list:
            bot.answer_callback_query(call.id, '📭 У тебя нет карт в этой коллекции!')
            return
        TRADE_PICK_STATE[call.from_user.id] = {'cards_list': cards_list, 'index': 0}
        _send_trade_card(ctx, call.message.chat.id, call.from_user.id)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data in {'trade_next', 'trade_prev'})
    def trade_navigate_card(call):
        if not antispam_callback(ctx, call, 'trade_nav', limit=10, window_seconds=3):
            return
        state = TRADE_PICK_STATE.get(call.from_user.id)
        if not state:
            bot.answer_callback_query(call.id, '❌ Список карт не найден.')
            return
        if call.data == 'trade_next':
            state['index'] = min(state['index'] + 1, len(state['cards_list']) - 1)
        else:
            state['index'] = max(state['index'] - 1, 0)
        _send_trade_card(ctx, call.message.chat.id, call.from_user.id)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith('trade_select_'))
    def trade_select_card(call):
        if not antispam_callback(ctx, call, 'trade_select', limit=4, window_seconds=3):
            return
        ensure_player(ctx, call.from_user)
        card_id = int(call.data.split('_')[2])
        if not ctx.db.get_user_card(call.from_user.id, card_id):
            bot.answer_callback_query(call.id, '❌ Карта не найдена.')
            return
        TRADE_DRAFTS[call.from_user.id] = card_id
        edit_or_send_text(ctx, call.message, 'Отправь @username пользователя, которому хочешь передать карту.', build_social_keyboard())
        bot.answer_callback_query(call.id)

    @bot.message_handler(func=lambda m: bool(m.text) and m.text.startswith('@'))
    def trade_enter_recipient(message):
        if not antispam_message(ctx, message, 'trade_recipient', limit=3, window_seconds=4):
            return
        ensure_player(ctx, message.from_user)
        sender_id = message.from_user.id
        card_id = TRADE_DRAFTS.get(sender_id)
        if not card_id:
            return
        recipient_username = message.text[1:].strip()
        recipient_id = ctx.db.get_user_id_by_username(recipient_username)
        if not recipient_id:
            bot.send_message(message.chat.id, f'❌ Пользователь @{recipient_username} не найден в базе.')
            return
        if recipient_id == sender_id:
            bot.send_message(message.chat.id, '❌ Нельзя отправить карту самому себе.')
            return
        card = ctx.db.get_user_card(sender_id, card_id)
        if not card:
            bot.send_message(message.chat.id, '❌ Карта уже недоступна.')
            TRADE_DRAFTS.pop(sender_id, None)
            return
        offer_id = ctx.db.create_trade_offer(sender_id, recipient_id, card_id)
        if not offer_id:
            bot.send_message(message.chat.id, '❌ Не получилось создать запрос. Возможно карта уже участвует в обмене.')
            return

        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton('✅ Принять', callback_data=f'offer_accept_{offer_id}'))
        keyboard.add(types.InlineKeyboardButton('❌ Отклонить', callback_data=f'offer_decline_{offer_id}'))

        sender_username = message.from_user.username or f'User{sender_id}'
        bot.send_message(recipient_id, format_trade_offer(card['artist'], card['name'], sender_username), reply_markup=keyboard)
        bot.send_message(message.chat.id, f'✅ Запрос отправлен @{recipient_username}', reply_markup=build_social_keyboard())
        ctx.db.log_event(sender_id, 'trade_offer_created', {'offer_id': offer_id, 'recipient_id': recipient_id})
        TRADE_DRAFTS.pop(sender_id, None)

    @bot.callback_query_handler(func=lambda c: c.data.startswith(('offer_accept_', 'offer_decline_')))
    def handle_trade_decision(call):
        if not antispam_callback(ctx, call, 'trade_decision', limit=4, window_seconds=3):
            return
        ensure_player(ctx, call.from_user)
        _, action, offer_id_raw = call.data.split('_')
        offer_id = int(offer_id_raw)
        offer = ctx.db.get_trade_offer(offer_id)
        if not offer or int(offer['recipient_id']) != call.from_user.id:
            bot.answer_callback_query(call.id, '❌ Этот запрос тебе не принадлежит.')
            return

        success, offer = ctx.db.resolve_trade_offer(offer_id, accept=(action == 'accept'))
        if action == 'decline':
            bot.edit_message_text('❌ Обмен отклонён.', call.message.chat.id, call.message.message_id)
            bot.send_message(int(offer['sender_id']), '❌ Твой запрос на обмен отклонён.')
            ctx.db.log_event(int(offer['sender_id']), 'trade_offer_declined', {'offer_id': offer_id})
            bot.answer_callback_query(call.id, 'Запрос отклонён.')
            return

        if not success:
            bot.edit_message_text('❌ Обмен не состоялся: карта недоступна.', call.message.chat.id, call.message.message_id)
            bot.answer_callback_query(call.id, 'Карта уже недоступна.')
            return

        card = ctx.db.get_user_card(call.from_user.id, int(offer['card_id']))
        bot.edit_message_text('✅ Обмен подтверждён!', call.message.chat.id, call.message.message_id)
        bot.send_message(int(offer['sender_id']), f'✅ Твоя карта {card["artist"]} — {card["name"]} успешно передана.')
        ctx.db.log_event(call.from_user.id, 'trade_offer_accepted', {'offer_id': offer_id})
        bot.answer_callback_query(call.id, 'Обмен завершён!')
