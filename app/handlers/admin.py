from __future__ import annotations

import logging

from app.context import AppContext
from app.data import CARD_POOL

logger = logging.getLogger(__name__)

# Telegram user IDs that are permitted to run admin commands.
ADMIN_IDS: set[int] = {123456789}


def register_admin_handlers(ctx: AppContext) -> None:
    bot = ctx.bot

    @bot.message_handler(commands=['giveallcards'])
    def give_all_cards(message) -> None:
        sender_id = message.from_user.id

        if sender_id not in ADMIN_IDS:
            bot.reply_to(message, '🚫 У тебя нет прав для этой команды.')
            return

        # Parse the username argument: /giveallcards @ygtmoves  or  /giveallcards ygtmoves
        parts = message.text.strip().split(maxsplit=1)
        if len(parts) < 2:
            bot.reply_to(message, '⚠️ Использование: /giveallcards @username')
            return

        raw_username = parts[1].lstrip('@').strip()
        if not raw_username:
            bot.reply_to(message, '⚠️ Укажи имя пользователя: /giveallcards @username')
            return

        target_id = ctx.db.get_user_id_by_username(raw_username)
        if target_id is None:
            bot.reply_to(
                message,
                f'❌ Пользователь <b>@{raw_username}</b> не найден в базе данных.\n'
                'Убедись, что он хотя бы раз запускал бота.',
            )
            return

        added = 0
        for rarity, cards in CARD_POOL.items():
            for card in cards:
                ctx.db.add_card(
                    user_id=target_id,
                    name=card['name'],
                    artist=card['artist'],
                    rarity=rarity,
                    acquired_from='admin_gift',
                )
                added += 1

        logger.info('Admin %s gave all %d cards to @%s (user_id=%d)', sender_id, added, raw_username, target_id)

        bot.reply_to(
            message,
            f'✅ Готово! <b>@{raw_username}</b> получил все <b>{added}</b> карточек из пула.',
        )
