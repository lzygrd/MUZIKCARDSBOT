from __future__ import annotations

import logging
from pathlib import Path

from telebot import types

from app.context import AppContext
from app.data import CARD_IMAGES
from app.keyboards import build_inline_menu, build_main_menu

logger = logging.getLogger(__name__)

INLINE_MENU_TEXT = '📋 <b>Меню</b>\n\nВыбери нужный раздел:'
HELP_TEXT = '\n'.join([
    'ℹ️ <b>Помощь по MUZCARD</b>',
    '',
    '🎴 Получить карту — бесплатная карта по кулдауну',
    '📋 Меню — открывает основные игровые разделы',
    '🤝 Социальное — баттлы, кланы, рынок, аукцион и обмен',
    '🎁 Ежедневная награда — XP или карта раз в сутки',
    '🛒 Магазин — покупки за XP, включая паки',
    '🎰 Рулетка — 4 карты на шанс апгрейда',
    '📚 Мои карты — просмотр коллекции',
    '',
    'Команды: /start /help /daily /stats',
])


def safe_send_card_media(ctx: AppContext, chat_id: int, text: str, artist: str, name: str, reply_markup: types.InlineKeyboardMarkup | None = None) -> None:
    image_path = CARD_IMAGES.get((artist, name))
    if image_path:
        resolved = Path(image_path)
        if resolved.exists():
            with resolved.open('rb') as photo:
                ctx.bot.send_photo(chat_id, photo, caption=text, reply_markup=reply_markup)
                return
    ctx.bot.send_message(chat_id, text, reply_markup=reply_markup)



def ensure_player(ctx: AppContext, user) -> None:
    ctx.db.ensure_user(user.id, user.username or f'User{user.id}', starter_xp=ctx.settings.starter_xp)



def antispam_message(ctx: AppContext, message, bucket: str, *, limit: int = 3, window_seconds: float = 2.5) -> bool:
    if ctx.antispam.hit(message.from_user.id, f'msg:{bucket}', limit=limit, window_seconds=window_seconds):
        return True
    ctx.bot.reply_to(message, '⏳ Не так быстро. Подожди чуть-чуть.')
    return False



def antispam_callback(ctx: AppContext, call, bucket: str, *, limit: int = 6, window_seconds: float = 2.5) -> bool:
    if ctx.antispam.hit(call.from_user.id, f'cb:{bucket}', limit=limit, window_seconds=window_seconds):
        return True
    ctx.bot.answer_callback_query(call.id, '⏳ Слишком быстро. Подожди секунду.', show_alert=False)
    return False



def send_inline_menu(ctx: AppContext, chat_id: int) -> None:
    ctx.bot.send_message(chat_id, INLINE_MENU_TEXT, reply_markup=build_inline_menu())



def edit_or_send_menu(ctx: AppContext, target) -> None:
    if hasattr(target, 'message_id'):
        try:
            ctx.bot.edit_message_text(INLINE_MENU_TEXT, target.chat.id, target.message_id, reply_markup=build_inline_menu())
            return
        except Exception:
            pass
        ctx.bot.send_message(target.chat.id, INLINE_MENU_TEXT, reply_markup=build_inline_menu())
        return
    send_inline_menu(ctx, target.chat.id)



def edit_or_send_text(ctx: AppContext, target, text: str, reply_markup: types.InlineKeyboardMarkup | None = None) -> None:
    if hasattr(target, 'message_id'):
        try:
            ctx.bot.edit_message_text(text, target.chat.id, target.message_id, reply_markup=reply_markup)
            return
        except Exception:
            pass
        ctx.bot.send_message(target.chat.id, text, reply_markup=reply_markup)
        return
    ctx.bot.send_message(target.chat.id, text, reply_markup=reply_markup)



def register_common_handlers(ctx: AppContext) -> None:
    bot = ctx.bot
    main_menu = build_main_menu()

    @bot.message_handler(commands=['start'])
    def start(message):
        if not antispam_message(ctx, message, 'start', limit=2, window_seconds=3):
            return
        ensure_player(ctx, message.from_user)
        caption = '🫆 <b>Добро пожаловать в MUZCARD</b>\n\nСобирай карточки, крути рулетку, открывай паки и качай XP.'
        if ctx.settings.hi_gif_path.exists():
            with ctx.settings.hi_gif_path.open('rb') as gif:
                bot.send_animation(message.chat.id, gif, caption=caption, reply_markup=main_menu)
        else:
            bot.send_message(message.chat.id, caption, reply_markup=main_menu)

    @bot.message_handler(commands=['help'])
    @bot.message_handler(func=lambda m: m.text == 'ℹ️ Помощь')
    def help_command(message):
        if not antispam_message(ctx, message, 'help'):
            return
        ensure_player(ctx, message.from_user)
        bot.send_message(message.chat.id, HELP_TEXT, reply_markup=main_menu)

    @bot.message_handler(commands=['stats'])
    def stats_command(message):
        if not antispam_message(ctx, message, 'stats'):
            return
        ensure_player(ctx, message.from_user)
        user_id = message.from_user.id
        cards = ctx.db.get_user_cards_count(user_id)
        events = ctx.db.get_recent_events(user_id, limit=5)
        lines = ['📊 <b>Статистика</b>', '', f'🎴 Карт: {cards}', f'🧾 Последних событий: {len(events)}']
        for row in events:
            lines.append(f'• {row["event_type"]}')
        bot.send_message(message.chat.id, '\n'.join(lines))

    @bot.message_handler(func=lambda m: m.text == '📋 Меню')
    def menu(message):
        if not antispam_message(ctx, message, 'menu'):
            return
        ensure_player(ctx, message.from_user)
        send_inline_menu(ctx, message.chat.id)

    @bot.callback_query_handler(func=lambda c: c.data == 'menu_back')
    def back_to_inline_menu(call):
        if not antispam_callback(ctx, call, 'menu_back'):
            return
        edit_or_send_menu(ctx, call.message)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == 'menu_close')
    def close_inline_menu(call):
        if not antispam_callback(ctx, call, 'menu_close'):
            return
        try:
            bot.edit_message_text('✅ Меню закрыто.', call.message.chat.id, call.message.message_id)
        except Exception:
            bot.send_message(call.message.chat.id, '✅ Меню закрыто.')
        bot.answer_callback_query(call.id)
