from __future__ import annotations

import html

from app.data import RARITY_LABELS


def escape(value: str | None) -> str:
    return html.escape(value or '')


def format_cooldown(seconds: int) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f'{seconds} сек'
    if seconds < 3600:
        minutes, sec = divmod(seconds, 60)
        return f'{minutes} мин' if sec == 0 else f'{minutes} мин {sec} сек'
    hours, rem = divmod(seconds, 3600)
    minutes, sec = divmod(rem, 60)
    result = f'{hours} ч'
    if minutes:
        result += f' {minutes} мин'
    if sec:
        result += f' {sec} сек'
    return result


def level_from_xp(xp: int) -> int:
    return max(1, xp // 250 + 1)


def format_card_text(card_id: int, artist: str, name: str, rarity: str, *, index: int | None = None, total: int | None = None, extra: str | None = None) -> str:
    lines = [
        f'<b>ID:</b> {card_id}',
        f'🎤 <b>{escape(artist)}</b>',
        f'💿 {escape(name)}',
        f'✨ {RARITY_LABELS.get(rarity, rarity)}',
    ]
    if index is not None and total is not None:
        lines.extend(['', f'Карта {index + 1} из {total}'])
    if extra:
        lines.extend(['', extra])
    return '\n'.join(lines)


def format_profile(user: dict, total_cards: int, rarity_counts: dict[str, int], next_collect_in: int, next_daily_in: int, *, battle: dict | None = None, clan_name: str | None = None, deck_size: int | None = None) -> str:
    xp = int(user['xp'])
    username = user['username'] or f'User{user["user_id"]}'
    safe_nick = f'@{escape(username)}' if not username.startswith('User') else escape(username)
    lines = [
        '👤 <b>ТВОЙ ПРОФИЛЬ</b>',
        '',
        f'Ник: {safe_nick}',
        f'⭐ Уровень: {level_from_xp(xp)}',
        f'⚡ XP: {xp}',
        f'🎴 Всего карт: {total_cards}',
        f'🎴 Single: {rarity_counts.get("single", 0)}',
        f'💿 Album: {rarity_counts.get("album", 0)}',
        f'✨ Limited: {rarity_counts.get("limited edition", 0)}',
        f'🔥 Daily streak: {int(user["daily_streak"])}',
    ]
    if battle:
        wins = int(battle.get('wins', 0))
        losses = int(battle.get('losses', 0))
        total = wins + losses
        winrate = int(round((wins / total) * 100)) if total else 0
        lines.extend([
            f'🏆 Рейтинг: {int(battle.get("rating", 1000))}',
            f'⚔️ Победы / поражения: {wins} / {losses}',
            f'📊 Винрейт: {winrate}%',
            f'🎴 В колоде: {deck_size or 0}/5',
        ])
    if clan_name:
        lines.append(f'👥 Клан: {escape(clan_name)}')
    lines.extend([
        '',
        f'🎁 Daily через: {format_cooldown(next_daily_in) if next_daily_in else "уже доступна"}',
        f'🎴 Карта через: {format_cooldown(next_collect_in) if next_collect_in else "уже доступна"}',
    ])
    return '\n'.join(lines)


def format_trade_offer(artist: str, name: str, sender_username: str) -> str:
    sender = escape(sender_username)
    sender = f'@{sender}' if not sender.startswith('User') else sender
    return f'📨 {sender} хочет передать тебе карту:\n🎤 <b>{escape(artist)}</b> — 💿 {escape(name)}\n\nПринять или отклонить?'
