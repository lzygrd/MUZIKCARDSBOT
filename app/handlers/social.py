from __future__ import annotations

import random
import time
from telebot import types

from app.context import AppContext
from app.data import RARITY_ALIASES, RARITY_LABELS
from app.handlers.common import antispam_callback, edit_or_send_text, ensure_player
from app.keyboards import build_collection_keyboard, build_social_keyboard
from app.utils.formatters import format_cooldown

SOCIAL_TEXT = '🤝 <b>Социальное</b>\n\nЗдесь живут баттлы, кланы, рынок, аукцион и обмен.'
MARKET_PICK_STATE: dict[int, dict] = {}
AUCTION_PICK_STATE: dict[int, dict] = {}
DECK_BUILD_STATE: dict[int, dict] = {}

RARITY_POWER = {
    'single': 40,
    'album': 75,
    'limited edition': 120,
}


# ---------- keyboards ----------
def _build_battles_keyboard() -> types.InlineKeyboardMarkup:
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton('🤖 Бой с ботом', callback_data='battle_bot'),
        types.InlineKeyboardButton('🎲 Случайный соперник', callback_data='battle_random'),
    )
    keyboard.add(
        types.InlineKeyboardButton('🎴 Моя колода', callback_data='battle_deck'),
        types.InlineKeyboardButton('🏆 Рейтинг', callback_data='battle_rank'),
    )
    keyboard.add(types.InlineKeyboardButton('🧾 История боёв', callback_data='battle_history'))
    keyboard.add(types.InlineKeyboardButton('⬅️ Назад в социальное', callback_data='menu_social'))
    return keyboard


def _build_deck_home_keyboard() -> types.InlineKeyboardMarkup:
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton('⚡ Автосборка', callback_data='battle_deck_auto'),
        types.InlineKeyboardButton('🛠 Собрать вручную', callback_data='battle_deck_pick'),
    )
    keyboard.add(types.InlineKeyboardButton('🗑 Очистить колоду', callback_data='battle_deck_clear'))
    keyboard.add(types.InlineKeyboardButton('⬅️ Назад к баттлам', callback_data='social_battles'))
    return keyboard


def _build_deck_rarity_keyboard() -> types.InlineKeyboardMarkup:
    keyboard = build_collection_keyboard(prefix='deck_rarity')
    keyboard.add(types.InlineKeyboardButton('⬅️ Назад к колоде', callback_data='battle_deck'))
    return keyboard


def _build_deck_pick_keyboard(state: dict, current_card_id: int) -> types.InlineKeyboardMarkup:
    total = len(state['cards'])
    idx = state['index']
    selected = set(state['selected'])
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    row = []
    if idx > 0:
        row.append(types.InlineKeyboardButton('⬅️ Назад', callback_data='deck_prev'))
    if idx < total - 1:
        row.append(types.InlineKeyboardButton('➡️ Вперёд', callback_data='deck_next'))
    if row:
        keyboard.row(*row)
    if current_card_id in selected:
        keyboard.add(types.InlineKeyboardButton('➖ Убрать карту', callback_data=f'deck_toggle_{current_card_id}'))
    else:
        keyboard.add(types.InlineKeyboardButton('➕ Добавить карту', callback_data=f'deck_toggle_{current_card_id}'))
    keyboard.add(types.InlineKeyboardButton('💾 Сохранить колоду', callback_data='deck_save'))
    keyboard.add(types.InlineKeyboardButton('⬅️ К выбору редкости', callback_data='battle_deck_pick'))
    return keyboard


def _build_clan_keyboard(clan, clans: list) -> types.InlineKeyboardMarkup:
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    if clan:
        keyboard.add(types.InlineKeyboardButton('🚪 Выйти из клана', callback_data='clan_leave'))
    else:
        keyboard.add(types.InlineKeyboardButton('➕ Создать свой клан', callback_data='clan_create'))
        for item in clans:
            keyboard.add(types.InlineKeyboardButton(f'👥 [{item["tag"]}] {item["name"]}', callback_data=f'clan_join_{item["id"]}'))
    keyboard.add(types.InlineKeyboardButton('🏆 Топ кланов', callback_data='clan_top'))
    keyboard.add(types.InlineKeyboardButton('🔄 Обновить', callback_data='social_clans'))
    keyboard.add(types.InlineKeyboardButton('⬅️ Назад в социальное', callback_data='menu_social'))
    return keyboard


def _build_market_keyboard(listings: list) -> types.InlineKeyboardMarkup:
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(types.InlineKeyboardButton('💸 Выставить карту', callback_data='market_sell'))
    for item in listings:
        keyboard.add(types.InlineKeyboardButton(f'🛍 Купить #{item["id"]} — {item["price"]} coins', callback_data=f'm_buy_{item["id"]}'))
    keyboard.add(types.InlineKeyboardButton('🔄 Обновить', callback_data='social_market'))
    keyboard.add(types.InlineKeyboardButton('⬅️ Назад в социальное', callback_data='menu_social'))
    return keyboard


def _build_auction_keyboard(auctions: list) -> types.InlineKeyboardMarkup:
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(types.InlineKeyboardButton('🔨 Запустить аукцион', callback_data='auction_sell'))
    for item in auctions:
        keyboard.add(types.InlineKeyboardButton(f'📣 Аукцион #{item["id"]} — {item["current_price"]} coins', callback_data=f'a_view_{item["id"]}'))
    keyboard.add(types.InlineKeyboardButton('🔄 Обновить', callback_data='social_auction'))
    keyboard.add(types.InlineKeyboardButton('⬅️ Назад в социальное', callback_data='menu_social'))
    return keyboard


def _build_pick_keyboard(prefix: str, index: int, total: int, card_id: int) -> types.InlineKeyboardMarkup:
    keyboard = types.InlineKeyboardMarkup()
    row = []
    if index > 0:
        row.append(types.InlineKeyboardButton('⬅️ Назад', callback_data=f'{prefix}_prev'))
    if index < total - 1:
        row.append(types.InlineKeyboardButton('➡️ Вперёд', callback_data=f'{prefix}_next'))
    if row:
        keyboard.row(*row)
    keyboard.add(types.InlineKeyboardButton('✅ Выбрать карту', callback_data=f'{prefix}_select_{card_id}'))
    keyboard.add(types.InlineKeyboardButton('⬅️ К выбору редкости', callback_data=f'{prefix}_pick_back'))
    keyboard.add(types.InlineKeyboardButton('🤝 Социальное', callback_data='menu_social'))
    return keyboard


def _build_market_price_keyboard(card_id: int) -> types.InlineKeyboardMarkup:
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    for price in (300, 600, 1000, 1500):
        keyboard.add(types.InlineKeyboardButton(f'{price} coins', callback_data=f'm_price_{card_id}_{price}'))
    keyboard.add(types.InlineKeyboardButton('⬅️ Назад к рынку', callback_data='social_market'))
    return keyboard


def _build_auction_price_keyboard(card_id: int) -> types.InlineKeyboardMarkup:
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    for price in (400, 800, 1200, 2000):
        keyboard.add(types.InlineKeyboardButton(f'{price} coins', callback_data=f'a_price_{card_id}_{price}'))
    keyboard.add(types.InlineKeyboardButton('⬅️ Назад к аукциону', callback_data='social_auction'))
    return keyboard


def _build_auction_view_keyboard(auction_id: int, current_price: int) -> types.InlineKeyboardMarkup:
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    for step in (100, 300, 500):
        keyboard.add(types.InlineKeyboardButton(f'+{step}', callback_data=f'a_bid_{auction_id}_{current_price + step}'))
    keyboard.add(types.InlineKeyboardButton('⬅️ Назад к аукционам', callback_data='social_auction'))
    return keyboard


# ---------- rendering ----------
def _send_social_menu(ctx: AppContext, target, user) -> None:
    ensure_player(ctx, user)
    edit_or_send_text(ctx, target, SOCIAL_TEXT, build_social_keyboard())


def _format_deck_line(slot: int, card) -> str:
    return f'{slot}. {RARITY_LABELS.get(card["rarity"], card["rarity"])} — <b>{card["artist"]}</b> / {card["name"]}'


def _render_deck_home(ctx: AppContext, target, user) -> None:
    ensure_player(ctx, user)
    deck = ctx.db.get_deck(user.id)
    lines = ['🎴 <b>Моя колода</b>', '']
    if deck:
        lines.append(f'Собрано карт: {len(deck)}/5')
        lines.append('')
        for card in deck:
            lines.append(_format_deck_line(int(card['slot']), card))
    else:
        lines.append('Колода пока не собрана.')
    lines.extend(['', 'Автосборка соберёт сильнейшие 5 карт. Ручная сборка позволит выбрать колоду самому.'])
    edit_or_send_text(ctx, target, '\n'.join(lines), _build_deck_home_keyboard())


def _render_battles(ctx: AppContext, target, user) -> None:
    ensure_player(ctx, user)
    rating = ctx.db.get_battle_profile(user.id)
    deck = ctx.db.get_deck(user.id)
    total = int(rating['wins']) + int(rating['losses'])
    winrate = int(round(int(rating['wins']) * 100 / total)) if total else 0
    text = (
        '⚔️ <b>Баттлы</b>\n\n'
        f'🏆 Рейтинг: {int(rating["rating"])}\n'
        f'Победы: {int(rating["wins"])}\n'
        f'Поражения: {int(rating["losses"])}\n'
        f'Винрейт: {winrate}%\n'
        f'Серия: {int(rating["streak"])}\n'
        f'Лучшая серия: {int(rating["best_streak"])}\n'
        f'Колода: {len(deck)}/5\n\n'
        'Выбери режим боя:'
    )
    edit_or_send_text(ctx, target, text, _build_battles_keyboard())


def _clan_tag_for(user) -> str:
    if getattr(user, 'username', None):
        raw = ''.join(ch for ch in user.username.upper() if ch.isalnum())
    else:
        raw = f'U{user.id}'
    return (raw[:6] or f'U{user.id}')


def _render_clans(ctx: AppContext, target, user) -> None:
    ensure_player(ctx, user)
    clan = ctx.db.get_user_clan(user.id)
    clans = ctx.db.list_clans(limit=6)
    if clan:
        lines = [
            '👥 <b>Кланы</b>',
            '',
            f'Твой клан: [{clan["tag"]}] {clan["name"]}',
            f'Роль: {clan["role"]}',
            f'Клановый XP: {clan["xp"]}',
            '',
            'Можешь остаться, посмотреть топ или выйти из клана.',
        ]
    else:
        lines = ['👥 <b>Кланы</b>', '', 'Ты пока не состоишь в клане.']
        if clans:
            lines.append('Открытые кланы:')
            for item in clans:
                lines.append(f'• [{item["tag"]}] {item["name"]} — {item["members_count"]} уч. / {item["xp"]} XP')
        else:
            lines.append('Пока нет ни одного клана. Создай первый!')
    edit_or_send_text(ctx, target, '\n'.join(lines), _build_clan_keyboard(clan, clans))


def _render_clan_top(ctx: AppContext, target) -> None:
    clans = ctx.db.list_clans(limit=10)
    lines = ['🏆 <b>Топ кланов</b>', '']
    if clans:
        for idx, clan in enumerate(clans, start=1):
            lines.append(f'{idx}. [{clan["tag"]}] {clan["name"]} — {clan["xp"]} XP • {clan["members_count"]} уч.')
    else:
        lines.append('Кланов пока нет.')
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton('⬅️ Назад к кланам', callback_data='social_clans'))
    edit_or_send_text(ctx, target, '\n'.join(lines), keyboard)


def _render_market(ctx: AppContext, target, user) -> None:
    ensure_player(ctx, user)
    stats = ctx.db.get_stats(user.id)
    listings = ctx.db.list_market_listings(limit=8)
    lines = ['🏪 <b>Рынок</b>', '', f'Твой баланс: {stats["coins"]} coins', '']
    if listings:
        for item in listings:
            lines.append(f'#{item["id"]} — <b>{item["artist"]}</b> / {item["name"]} • {item["price"]} coins')
    else:
        lines.append('Сейчас активных лотов нет.')
    edit_or_send_text(ctx, target, '\n'.join(lines), _build_market_keyboard(listings))


def _render_auction(ctx: AppContext, target, user) -> None:
    ensure_player(ctx, user)
    stats = ctx.db.get_stats(user.id)
    auctions = ctx.db.list_auctions(limit=8)
    lines = ['🔨 <b>Аукцион</b>', '', f'Твой баланс: {stats["coins"]} coins', '']
    if auctions:
        now = time.time()
        for item in auctions:
            remaining = max(0, int(float(item['ends_at']) - now))
            lines.append(f'#{item["id"]} — <b>{item["artist"]}</b> / {item["name"]} • {item["current_price"]} coins • {format_cooldown(remaining)}')
    else:
        lines.append('Активных аукционов нет.')
    edit_or_send_text(ctx, target, '\n'.join(lines), _build_auction_keyboard(auctions))


def _show_pick_card(ctx: AppContext, chat_id: int, user_id: int, state: dict, prefix: str) -> None:
    cards_list = state['cards_list']
    index = state['index']
    card = cards_list[index]
    purpose = 'рынка' if prefix == 'market' else 'аукциона'
    text = (
        f'<b>ID:</b> {card["id"]}\n'
        f'🎤 <b>{card["artist"]}</b>\n'
        f'💿 {card["name"]}\n'
        f'✨ {RARITY_LABELS.get(card["rarity"], card["rarity"])}\n\n'
        f'Карта {index + 1} из {len(cards_list)}\n\n'
        f'Выбери карту для {purpose}.'
    )
    ctx.bot.send_message(chat_id, text, reply_markup=_build_pick_keyboard(prefix, index, len(cards_list), card['id']))


def _render_deck_picker(ctx: AppContext, target, user_id: int) -> None:
    state = DECK_BUILD_STATE.get(user_id)
    if not state or not state.get('cards'):
        edit_or_send_text(ctx, target, '🎴 <b>Выбор карт для колоды</b>\n\nСначала выбери редкость.', _build_deck_rarity_keyboard())
        return
    cards = state['cards']
    idx = state['index']
    current = cards[idx]
    selected = state['selected']
    lines = [
        '🎴 <b>Сборка колоды</b>',
        '',
        f'Редкость: {RARITY_LABELS.get(state["rarity"], state["rarity"])}',
        f'Карта {idx + 1} из {len(cards)}',
        '',
        f'<b>ID:</b> {current["id"]}',
        f'🎤 <b>{current["artist"]}</b>',
        f'💿 {current["name"]}',
        f'✨ {RARITY_LABELS.get(current["rarity"], current["rarity"])}',
        '',
        f'Выбрано: {len(selected)}/5',
    ]
    if selected:
        lines.append('Слоты: ' + ', '.join(str(card_id) for card_id in selected))
    edit_or_send_text(ctx, target, '\n'.join(lines), _build_deck_pick_keyboard(state, int(current['id'])))


def _prepare_deck_for_battle(ctx: AppContext, user_id: int) -> tuple[list, str | None]:
    deck = ctx.db.get_deck(user_id)
    if len(deck) == 5:
        return deck, None
    ok, _ = ctx.db.auto_build_deck(user_id)
    deck = ctx.db.get_deck(user_id)
    if len(deck) != 5:
        return [], 'Для баттла нужно минимум 5 карт. Собери колоду в разделе «Моя колода».'
    return deck, None


def _deck_score(deck: list[dict] | list) -> tuple[int, list[str]]:
    score = 0
    details: list[str] = []
    artists: dict[str, int] = {}
    rarities: set[str] = set()
    for card in deck:
        rarity = str(card['rarity'])
        score += RARITY_POWER.get(rarity, 35)
        artists[str(card['artist'])] = artists.get(str(card['artist']), 0) + 1
        rarities.add(rarity)
    if len(rarities) == 3:
        score += 30
        details.append('+30 за полный набор редкостей')
    same_artist_bonus = sum((count - 1) * 12 for count in artists.values() if count > 1)
    if same_artist_bonus:
        score += same_artist_bonus
        details.append(f'+{same_artist_bonus} за синергию артистов')
    random_bonus = random.randint(0, 45)
    score += random_bonus
    details.append(f'+{random_bonus} случайный бонус')
    return score, details


def _deck_preview(deck: list) -> str:
    parts = []
    for card in deck[:5]:
        parts.append(f'• <b>{card["artist"]}</b> / {card["name"]}')
    return '\n'.join(parts)


def _run_battle(ctx: AppContext, target, user, opponent_id: int | None, opponent_name: str, mode: str) -> None:
    ensure_player(ctx, user)
    my_deck, error = _prepare_deck_for_battle(ctx, user.id)
    if error:
        edit_or_send_text(ctx, target, f'❌ {error}', _build_battles_keyboard())
        return

    if opponent_id:
        ensure_player(ctx, type('TmpUser', (), {'id': opponent_id, 'username': None})())
        enemy_deck, _ = _prepare_deck_for_battle(ctx, opponent_id)
        if len(enemy_deck) != 5:
            opponent_id = None
            opponent_name = 'Бот MUZCARD'
            mode = 'bot'
    if not opponent_id:
        sample = []
        pool_rows = ctx.db.fetchall(
            '''
            SELECT id, name, artist, rarity FROM user_cards
            WHERE user_id != ?
            ORDER BY CASE rarity WHEN 'limited edition' THEN 3 WHEN 'album' THEN 2 ELSE 1 END DESC, RANDOM()
            LIMIT 5
            ''',
            (user.id,),
        )
        if len(pool_rows) >= 5:
            sample = pool_rows
        else:
            from app.services.game_logic import random_card
            sample = [dict(id=0, **random_card()) for _ in range(5)]
        enemy_deck = sample

    my_score, my_details = _deck_score(my_deck)
    enemy_score, enemy_details = _deck_score(enemy_deck)
    won = my_score >= enemy_score
    reward_xp = 160 if won else 65
    reward_coins = 320 if won else 120
    rating_delta = 25 if won else -15
    if mode == 'bot':
        rating_delta = 18 if won else -10
    ctx.db.add_xp(user.id, reward_xp)
    ctx.db.add_coins(user.id, reward_coins)
    ctx.db.update_battle_rating(user.id, won=won, delta=rating_delta)
    if opponent_id:
        ctx.db.update_battle_rating(opponent_id, won=not won, delta=(-rating_delta if mode != 'bot' else 0))
    winner_id = user.id if won else (opponent_id or 0)
    loser_id = (opponent_id or 0) if won else user.id
    ctx.db.record_battle(user.id, opponent_id or 0, winner_id, loser_id, my_score, enemy_score, mode=mode)
    user_clan = ctx.db.get_user_clan(user.id)
    if user_clan:
        ctx.db.add_clan_xp(int(user_clan['id']), 40 if won else 15)
    if opponent_id and won:
        opp_clan = ctx.db.get_user_clan(opponent_id)
        if opp_clan:
            ctx.db.add_clan_xp(int(opp_clan['id']), 8)
    ctx.db.log_event(user.id, 'battle_result', {'mode': mode, 'won': won, 'score': my_score, 'enemy_score': enemy_score})

    rating = ctx.db.get_battle_profile(user.id)
    lines = [
        '⚔️ <b>Результат баттла</b>',
        '',
        f'Ты vs {opponent_name}',
        f'Твоя сила: {my_score}',
        f'Сила соперника: {enemy_score}',
        '',
        '🎴 Твоя колода:',
        _deck_preview(my_deck),
        '',
        ('🏆 <b>Победа!</b>' if won else '💥 <b>Поражение!</b>'),
        f'⚡ +{reward_xp} XP',
        f'💰 +{reward_coins} coins',
        f'🏆 Рейтинг: {int(rating["rating"])} ({rating_delta:+d})',
    ]
    if my_details:
        lines.extend(['', 'Бонусы:', *[f'• {item}' for item in my_details]])
    edit_or_send_text(ctx, target, '\n'.join(lines), _build_battles_keyboard())


# ---------- handlers ----------
def register_social_handlers(ctx: AppContext) -> None:
    bot = ctx.bot

    @bot.callback_query_handler(func=lambda c: c.data == 'menu_social')
    def open_social(call):
        if not antispam_callback(ctx, call, 'menu_social'):
            return
        _send_social_menu(ctx, call.message, call.from_user)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == 'social_battles')
    def social_battles(call):
        if not antispam_callback(ctx, call, 'social_battles'):
            return
        _render_battles(ctx, call.message, call.from_user)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == 'battle_deck')
    def battle_deck(call):
        if not antispam_callback(ctx, call, 'battle_deck'):
            return
        _render_deck_home(ctx, call.message, call.from_user)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == 'battle_deck_auto')
    def battle_deck_auto(call):
        if not antispam_callback(ctx, call, 'battle_deck_auto'):
            return
        ok, message = ctx.db.auto_build_deck(call.from_user.id)
        bot.answer_callback_query(call.id, message)
        _render_deck_home(ctx, call.message, call.from_user)

    @bot.callback_query_handler(func=lambda c: c.data == 'battle_deck_clear')
    def battle_deck_clear(call):
        if not antispam_callback(ctx, call, 'battle_deck_clear'):
            return
        ctx.db.clear_deck(call.from_user.id)
        bot.answer_callback_query(call.id, 'Колода очищена.')
        _render_deck_home(ctx, call.message, call.from_user)

    @bot.callback_query_handler(func=lambda c: c.data == 'battle_deck_pick')
    def battle_deck_pick(call):
        if not antispam_callback(ctx, call, 'battle_deck_pick'):
            return
        selected = [int(card['id']) for card in ctx.db.get_deck(call.from_user.id)]
        DECK_BUILD_STATE[call.from_user.id] = {'selected': selected, 'cards': [], 'index': 0, 'rarity': 'single'}
        edit_or_send_text(ctx, call.message, '🎴 <b>Сборка колоды</b>\n\nВыбери редкость, из которой хочешь добавить карту.', _build_deck_rarity_keyboard())
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith('deck_rarity_'))
    def deck_rarity(call):
        if not antispam_callback(ctx, call, 'deck_rarity'):
            return
        rarity_key = call.data.split('_', maxsplit=2)[2]
        rarity = RARITY_ALIASES.get(rarity_key, 'single')
        cards = ctx.db.get_user_cards_by_rarity(call.from_user.id, rarity)
        if not cards:
            bot.answer_callback_query(call.id, '📭 У тебя нет карт этой редкости.')
            return
        state = DECK_BUILD_STATE.get(call.from_user.id) or {'selected': [], 'cards': [], 'index': 0, 'rarity': rarity}
        state['cards'] = cards
        state['index'] = 0
        state['rarity'] = rarity
        DECK_BUILD_STATE[call.from_user.id] = state
        _render_deck_picker(ctx, call.message, call.from_user.id)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data in {'deck_prev', 'deck_next'})
    def deck_nav(call):
        if not antispam_callback(ctx, call, 'deck_nav', limit=10, window_seconds=3):
            return
        state = DECK_BUILD_STATE.get(call.from_user.id)
        if not state or not state.get('cards'):
            bot.answer_callback_query(call.id, 'Сначала выбери редкость.')
            return
        if call.data == 'deck_next':
            state['index'] = min(state['index'] + 1, len(state['cards']) - 1)
        else:
            state['index'] = max(state['index'] - 1, 0)
        _render_deck_picker(ctx, call.message, call.from_user.id)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith('deck_toggle_'))
    def deck_toggle(call):
        if not antispam_callback(ctx, call, 'deck_toggle', limit=8, window_seconds=3):
            return
        state = DECK_BUILD_STATE.get(call.from_user.id)
        if not state:
            bot.answer_callback_query(call.id, 'Сначала начни сборку колоды.')
            return
        card_id = int(call.data.split('_')[2])
        selected = state['selected']
        if card_id in selected:
            selected.remove(card_id)
            bot.answer_callback_query(call.id, 'Карта убрана из колоды.')
        else:
            if len(selected) >= 5:
                bot.answer_callback_query(call.id, 'В колоде уже 5 карт.')
                return
            selected.append(card_id)
            bot.answer_callback_query(call.id, 'Карта добавлена в колоду.')
        _render_deck_picker(ctx, call.message, call.from_user.id)

    @bot.callback_query_handler(func=lambda c: c.data == 'deck_save')
    def deck_save(call):
        if not antispam_callback(ctx, call, 'deck_save'):
            return
        state = DECK_BUILD_STATE.get(call.from_user.id)
        if not state:
            bot.answer_callback_query(call.id, 'Сначала начни сборку колоды.')
            return
        ok, message = ctx.db.save_deck(call.from_user.id, state['selected'])
        bot.answer_callback_query(call.id, message)
        _render_deck_home(ctx, call.message, call.from_user)

    @bot.callback_query_handler(func=lambda c: c.data == 'battle_bot')
    def battle_bot(call):
        if not antispam_callback(ctx, call, 'battle_bot'):
            return
        _run_battle(ctx, call.message, call.from_user, None, 'Бот MUZCARD', 'bot')
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == 'battle_random')
    def battle_random(call):
        if not antispam_callback(ctx, call, 'battle_random'):
            return
        ensure_player(ctx, call.from_user)
        opponents = [row for row in ctx.db.get_top_users(limit=30) if int(row['user_id']) != call.from_user.id]
        if not opponents:
            _run_battle(ctx, call.message, call.from_user, None, 'Бот MUZCARD', 'bot')
            bot.answer_callback_query(call.id, 'Соперников нет, запустили бой с ботом.')
            return
        opponent = random.choice(opponents)
        opponent_name = f'@{opponent["username"]}' if opponent['username'] and not str(opponent['username']).startswith('User') else f'User{opponent["user_id"]}'
        _run_battle(ctx, call.message, call.from_user, int(opponent['user_id']), opponent_name, 'pvp')
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == 'battle_rank')
    def battle_rank(call):
        if not antispam_callback(ctx, call, 'battle_rank'):
            return
        rows = ctx.db.get_battle_leaderboard(limit=10)
        lines = ['🏆 <b>Рейтинг баттлов</b>', '']
        for idx, row in enumerate(rows, start=1):
            username = row['username'] or f'User{row["user_id"]}'
            prefix = '@' if not str(username).startswith('User') else ''
            lines.append(f'{idx}. {prefix}{username} — {row["rating"]} MMR • {row["wins"]}/{row["losses"]}')
        edit_or_send_text(ctx, call.message, '\n'.join(lines), _build_battles_keyboard())
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == 'battle_history')
    def battle_history(call):
        if not antispam_callback(ctx, call, 'battle_history'):
            return
        rows = ctx.db.get_recent_battles_detailed(call.from_user.id, limit=8)
        lines = ['🧾 <b>Последние баттлы</b>', '']
        if rows:
            for row in rows:
                enemy = row['defender_username'] if int(row['attacker_id']) == call.from_user.id else row['attacker_username']
                mode = '🤖' if row['mode'] == 'bot' else '⚔️'
                result = 'Победа' if int(row['winner_id']) == call.from_user.id else 'Поражение'
                lines.append(f'{mode} vs {enemy}: {row["attacker_score"]}:{row["defender_score"]} — {result}')
        else:
            lines.append('История пока пустая.')
        edit_or_send_text(ctx, call.message, '\n'.join(lines), _build_battles_keyboard())
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == 'social_clans')
    def social_clans(call):
        if not antispam_callback(ctx, call, 'social_clans'):
            return
        _render_clans(ctx, call.message, call.from_user)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == 'clan_top')
    def clan_top(call):
        if not antispam_callback(ctx, call, 'clan_top'):
            return
        _render_clan_top(ctx, call.message)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == 'clan_create')
    def clan_create(call):
        if not antispam_callback(ctx, call, 'clan_create'):
            return
        ensure_player(ctx, call.from_user)
        base_tag = _clan_tag_for(call.from_user)
        tag = base_tag
        existing_tags = {str(item['tag']) for item in ctx.db.list_clans(limit=200)}
        suffix = 1
        while tag in existing_tags:
            suffix += 1
            tag = f'{base_tag[:4]}{suffix}'[:10]
        clan_name = f'Клан {call.from_user.username or call.from_user.id}'
        ok, message = ctx.db.create_clan(call.from_user.id, tag, clan_name)
        if ok:
            ctx.db.log_event(call.from_user.id, 'clan_created', {'tag': tag})
        bot.answer_callback_query(call.id, message)
        _render_clans(ctx, call.message, call.from_user)

    @bot.callback_query_handler(func=lambda c: c.data.startswith('clan_join_'))
    def clan_join(call):
        if not antispam_callback(ctx, call, 'clan_join'):
            return
        clan_id = int(call.data.split('_')[2])
        ok, message = ctx.db.join_clan(call.from_user.id, clan_id)
        if ok:
            clan = ctx.db.get_user_clan(call.from_user.id)
            if clan:
                ctx.db.log_event(call.from_user.id, 'clan_joined', {'tag': clan['tag']})
        bot.answer_callback_query(call.id, message)
        _render_clans(ctx, call.message, call.from_user)

    @bot.callback_query_handler(func=lambda c: c.data == 'clan_leave')
    def clan_leave(call):
        if not antispam_callback(ctx, call, 'clan_leave'):
            return
        ok, message = ctx.db.leave_clan(call.from_user.id)
        bot.answer_callback_query(call.id, message)
        _render_clans(ctx, call.message, call.from_user)

    @bot.callback_query_handler(func=lambda c: c.data == 'social_market')
    def social_market(call):
        if not antispam_callback(ctx, call, 'social_market'):
            return
        _render_market(ctx, call.message, call.from_user)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == 'market_sell')
    def market_sell(call):
        if not antispam_callback(ctx, call, 'market_sell'):
            return
        ensure_player(ctx, call.from_user)
        edit_or_send_text(ctx, call.message, '🏪 <b>Выставить карту</b>\n\nСначала выбери редкость карты:', build_collection_keyboard(prefix='market_collection'))
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith('market_collection_'))
    def market_collection(call):
        if not antispam_callback(ctx, call, 'market_collection', limit=8, window_seconds=3):
            return
        rarity_key = call.data.split('_', maxsplit=2)[2]
        rarity = RARITY_ALIASES.get(rarity_key, 'single')
        cards = ctx.db.get_user_cards_by_rarity(call.from_user.id, rarity)
        if not cards:
            bot.answer_callback_query(call.id, '📭 В этой коллекции нет карт.')
            return
        MARKET_PICK_STATE[call.from_user.id] = {'cards_list': cards, 'index': 0}
        _show_pick_card(ctx, call.message.chat.id, call.from_user.id, MARKET_PICK_STATE[call.from_user.id], 'market')
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data in {'market_prev', 'market_next'})
    def market_nav(call):
        if not antispam_callback(ctx, call, 'market_nav', limit=10, window_seconds=3):
            return
        state = MARKET_PICK_STATE.get(call.from_user.id)
        if not state:
            bot.answer_callback_query(call.id, 'Сначала выбери редкость.')
            return
        state['index'] = min(state['index'] + 1, len(state['cards_list']) - 1) if call.data.endswith('next') else max(state['index'] - 1, 0)
        _show_pick_card(ctx, call.message.chat.id, call.from_user.id, state, 'market')
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == 'market_pick_back')
    def market_back(call):
        if not antispam_callback(ctx, call, 'market_back'):
            return
        edit_or_send_text(ctx, call.message, '🏪 <b>Выставить карту</b>\n\nСначала выбери редкость карты:', build_collection_keyboard(prefix='market_collection'))
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith('market_select_'))
    def market_select(call):
        if not antispam_callback(ctx, call, 'market_select', limit=6, window_seconds=3):
            return
        card_id = int(call.data.split('_')[2])
        card = ctx.db.get_user_card(call.from_user.id, card_id)
        if not card:
            bot.answer_callback_query(call.id, 'Карта не найдена.')
            return
        text = (
            f'<b>ID:</b> {card["id"]}\n🎤 <b>{card["artist"]}</b>\n💿 {card["name"]}\n✨ {RARITY_LABELS.get(card["rarity"], card["rarity"])}\n\nВыбери цену для лота.'
        )
        edit_or_send_text(ctx, call.message, text, _build_market_price_keyboard(card_id))
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith('m_price_'))
    def market_price(call):
        if not antispam_callback(ctx, call, 'market_price', limit=5, window_seconds=3):
            return
        _, _, card_id_raw, price_raw = call.data.split('_')
        ok, message = ctx.db.create_market_listing(call.from_user.id, int(card_id_raw), int(price_raw))
        if ok:
            ctx.db.log_event(call.from_user.id, 'market_listing_created', {'card_id': int(card_id_raw), 'price': int(price_raw)})
        bot.answer_callback_query(call.id, message)
        _render_market(ctx, call.message, call.from_user)

    @bot.callback_query_handler(func=lambda c: c.data.startswith('m_buy_'))
    def market_buy(call):
        if not antispam_callback(ctx, call, 'market_buy', limit=4, window_seconds=3):
            return
        listing_id = int(call.data.split('_')[2])
        ok, message = ctx.db.buy_market_listing(call.from_user.id, listing_id)
        if ok:
            ctx.db.log_event(call.from_user.id, 'market_listing_bought', {'listing_id': listing_id})
        bot.answer_callback_query(call.id, message)
        _render_market(ctx, call.message, call.from_user)

    @bot.callback_query_handler(func=lambda c: c.data == 'social_auction')
    def social_auction(call):
        if not antispam_callback(ctx, call, 'social_auction'):
            return
        _render_auction(ctx, call.message, call.from_user)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == 'auction_sell')
    def auction_sell(call):
        if not antispam_callback(ctx, call, 'auction_sell'):
            return
        ensure_player(ctx, call.from_user)
        edit_or_send_text(ctx, call.message, '🔨 <b>Запустить аукцион</b>\n\nСначала выбери редкость карты:', build_collection_keyboard(prefix='auction_collection'))
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith('auction_collection_'))
    def auction_collection(call):
        if not antispam_callback(ctx, call, 'auction_collection', limit=8, window_seconds=3):
            return
        rarity_key = call.data.split('_', maxsplit=2)[2]
        rarity = RARITY_ALIASES.get(rarity_key, 'single')
        cards = ctx.db.get_user_cards_by_rarity(call.from_user.id, rarity)
        if not cards:
            bot.answer_callback_query(call.id, '📭 В этой коллекции нет карт.')
            return
        AUCTION_PICK_STATE[call.from_user.id] = {'cards_list': cards, 'index': 0}
        _show_pick_card(ctx, call.message.chat.id, call.from_user.id, AUCTION_PICK_STATE[call.from_user.id], 'auction')
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data in {'auction_prev', 'auction_next'})
    def auction_nav(call):
        if not antispam_callback(ctx, call, 'auction_nav', limit=10, window_seconds=3):
            return
        state = AUCTION_PICK_STATE.get(call.from_user.id)
        if not state:
            bot.answer_callback_query(call.id, 'Сначала выбери редкость.')
            return
        state['index'] = min(state['index'] + 1, len(state['cards_list']) - 1) if call.data.endswith('next') else max(state['index'] - 1, 0)
        _show_pick_card(ctx, call.message.chat.id, call.from_user.id, state, 'auction')
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == 'auction_pick_back')
    def auction_back(call):
        if not antispam_callback(ctx, call, 'auction_back'):
            return
        edit_or_send_text(ctx, call.message, '🔨 <b>Запустить аукцион</b>\n\nСначала выбери редкость карты:', build_collection_keyboard(prefix='auction_collection'))
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith('auction_select_'))
    def auction_select(call):
        if not antispam_callback(ctx, call, 'auction_select', limit=6, window_seconds=3):
            return
        card_id = int(call.data.split('_')[2])
        card = ctx.db.get_user_card(call.from_user.id, card_id)
        if not card:
            bot.answer_callback_query(call.id, 'Карта не найдена.')
            return
        text = (
            f'<b>ID:</b> {card["id"]}\n🎤 <b>{card["artist"]}</b>\n💿 {card["name"]}\n✨ {RARITY_LABELS.get(card["rarity"], card["rarity"])}\n\nВыбери стартовую цену аукциона (длительность 12 часов).'
        )
        edit_or_send_text(ctx, call.message, text, _build_auction_price_keyboard(card_id))
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith('a_price_'))
    def auction_price(call):
        if not antispam_callback(ctx, call, 'auction_price', limit=5, window_seconds=3):
            return
        _, _, card_id_raw, price_raw = call.data.split('_')
        ok, message = ctx.db.create_auction(call.from_user.id, int(card_id_raw), int(price_raw), duration_hours=12)
        if ok:
            ctx.db.log_event(call.from_user.id, 'auction_created', {'card_id': int(card_id_raw), 'price': int(price_raw)})
        bot.answer_callback_query(call.id, message)
        _render_auction(ctx, call.message, call.from_user)

    @bot.callback_query_handler(func=lambda c: c.data.startswith('a_view_'))
    def auction_view(call):
        if not antispam_callback(ctx, call, 'auction_view'):
            return
        auction_id = int(call.data.split('_')[2])
        auction = ctx.db.get_auction(auction_id)
        if not auction or auction['status'] != 'active':
            bot.answer_callback_query(call.id, 'Аукцион уже недоступен.')
            _render_auction(ctx, call.message, call.from_user)
            return
        remaining = max(0, int(float(auction['ends_at']) - time.time()))
        bidder = auction['highest_bidder_id'] or 'пока нет'
        text = (
            '🔨 <b>Аукцион</b>\n\n'
            f'Лот #{auction["id"]}\n'
            f'🎤 <b>{auction["artist"]}</b>\n'
            f'💿 {auction["name"]}\n'
            f'✨ {RARITY_LABELS.get(auction["rarity"], auction["rarity"])}\n\n'
            f'Текущая ставка: {auction["current_price"]} coins\n'
            f'Лидер: {bidder}\n'
            f'До конца: {format_cooldown(remaining)}'
        )
        edit_or_send_text(ctx, call.message, text, _build_auction_view_keyboard(auction_id, int(auction['current_price'])))
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith('a_bid_'))
    def auction_bid(call):
        if not antispam_callback(ctx, call, 'auction_bid', limit=5, window_seconds=3):
            return
        _, _, auction_id_raw, amount_raw = call.data.split('_')
        ok, message = ctx.db.place_bid(call.from_user.id, int(auction_id_raw), int(amount_raw))
        if ok:
            ctx.db.log_event(call.from_user.id, 'auction_bid', {'auction_id': int(auction_id_raw), 'amount': int(amount_raw)})
        bot.answer_callback_query(call.id, message)
        auction = ctx.db.get_auction(int(auction_id_raw))
        if auction and auction['status'] == 'active':
            remaining = max(0, int(float(auction['ends_at']) - time.time()))
            bidder = auction['highest_bidder_id'] or 'пока нет'
            text = (
                '🔨 <b>Аукцион</b>\n\n'
                f'Лот #{auction["id"]}\n'
                f'🎤 <b>{auction["artist"]}</b>\n'
                f'💿 {auction["name"]}\n'
                f'✨ {RARITY_LABELS.get(auction["rarity"], auction["rarity"])}\n\n'
                f'Текущая ставка: {auction["current_price"]} coins\n'
                f'Лидер: {bidder}\n'
                f'До конца: {format_cooldown(remaining)}'
            )
            edit_or_send_text(ctx, call.message, text, _build_auction_view_keyboard(int(auction_id_raw), int(auction['current_price'])))
        else:
            _render_auction(ctx, call.message, call.from_user)
