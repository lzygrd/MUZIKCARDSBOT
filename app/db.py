from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Callable


class Database:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._bootstrap()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys = ON')
        conn.execute('PRAGMA busy_timeout = 3000')
        return conn

    def _bootstrap(self) -> None:
        with self._connect() as conn:
            conn.execute('PRAGMA journal_mode = WAL')
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    xp INTEGER NOT NULL DEFAULT 0,
                    last_daily REAL NOT NULL DEFAULT 0,
                    last_collect REAL NOT NULL DEFAULT 0,
                    daily_streak INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
                    updated_at REAL NOT NULL DEFAULT (strftime('%s','now'))
                )
                '''
            )
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS user_cards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    artist TEXT NOT NULL,
                    rarity TEXT NOT NULL,
                    acquired_from TEXT NOT NULL DEFAULT 'unknown',
                    created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                )
                '''
            )
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS trade_offers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender_id INTEGER NOT NULL,
                    recipient_id INTEGER NOT NULL,
                    card_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
                    responded_at REAL
                )
                '''
            )
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS user_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
                )
                '''
            )
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS user_stats (
                    user_id INTEGER PRIMARY KEY,
                    xp INTEGER DEFAULT 0,
                    level INTEGER DEFAULT 1,
                    coins INTEGER DEFAULT 0,
                    gems INTEGER DEFAULT 0
                )
                '''
            )
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS daily_tasks (
                    user_id INTEGER,
                    task TEXT,
                    progress INTEGER DEFAULT 0
                )
                '''
            )
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS clans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tag TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    owner_id INTEGER NOT NULL,
                    xp INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
                )
                '''
            )
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS clan_members (
                    clan_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL UNIQUE,
                    role TEXT NOT NULL DEFAULT 'member',
                    joined_at REAL NOT NULL DEFAULT (strftime('%s','now')),
                    PRIMARY KEY (clan_id, user_id),
                    FOREIGN KEY (clan_id) REFERENCES clans(id) ON DELETE CASCADE
                )
                '''
            )
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS market_listings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    seller_id INTEGER NOT NULL,
                    buyer_id INTEGER,
                    card_id INTEGER NOT NULL UNIQUE,
                    price INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
                    sold_at REAL
                )
                '''
            )
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS auctions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    seller_id INTEGER NOT NULL,
                    card_id INTEGER NOT NULL UNIQUE,
                    start_price INTEGER NOT NULL,
                    current_price INTEGER NOT NULL,
                    highest_bidder_id INTEGER,
                    status TEXT NOT NULL DEFAULT 'active',
                    ends_at REAL NOT NULL,
                    created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
                    resolved_at REAL
                )
                '''
            )
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS battles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    attacker_id INTEGER NOT NULL,
                    defender_id INTEGER NOT NULL,
                    winner_id INTEGER NOT NULL,
                    loser_id INTEGER NOT NULL,
                    attacker_score INTEGER NOT NULL,
                    defender_score INTEGER NOT NULL,
                    mode TEXT NOT NULL DEFAULT 'pvp',
                    created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
                )
                '''
            )

            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS user_decks (
                    user_id INTEGER NOT NULL,
                    slot INTEGER NOT NULL,
                    card_id INTEGER NOT NULL,
                    PRIMARY KEY (user_id, slot),
                    FOREIGN KEY (card_id) REFERENCES user_cards(id) ON DELETE CASCADE
                )
                '''
            )
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS user_ratings (
                    user_id INTEGER PRIMARY KEY,
                    rating INTEGER NOT NULL DEFAULT 1000,
                    wins INTEGER NOT NULL DEFAULT 0,
                    losses INTEGER NOT NULL DEFAULT 0,
                    streak INTEGER NOT NULL DEFAULT 0,
                    best_streak INTEGER NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL DEFAULT (strftime('%s','now'))
                )
                '''
            )
            self._migrate(conn)
            conn.commit()

    def _migrate(self, conn: sqlite3.Connection) -> None:
        columns = {row['name'] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
        wanted = {
            'last_collect': "ALTER TABLE users ADD COLUMN last_collect REAL NOT NULL DEFAULT 0",
            'daily_streak': "ALTER TABLE users ADD COLUMN daily_streak INTEGER NOT NULL DEFAULT 0",
            'created_at': "ALTER TABLE users ADD COLUMN created_at REAL NOT NULL DEFAULT 0",
            'updated_at': "ALTER TABLE users ADD COLUMN updated_at REAL NOT NULL DEFAULT 0",
        }
        for col, ddl in wanted.items():
            if col not in columns:
                conn.execute(ddl)

        card_columns = {row['name'] for row in conn.execute("PRAGMA table_info(user_cards)").fetchall()}
        if 'acquired_from' not in card_columns:
            conn.execute("ALTER TABLE user_cards ADD COLUMN acquired_from TEXT NOT NULL DEFAULT 'unknown'")
        if 'created_at' not in card_columns:
            conn.execute("ALTER TABLE user_cards ADD COLUMN created_at REAL NOT NULL DEFAULT 0")

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(query, params)
            conn.commit()

    def fetchone(self, query: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        with self._lock, self._connect() as conn:
            return conn.execute(query, params).fetchone()

    def fetchall(self, query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self._lock, self._connect() as conn:
            return conn.execute(query, params).fetchall()

    def transaction(self, func: Callable[[sqlite3.Connection], Any]) -> Any:
        with self._lock, self._connect() as conn:
            result = func(conn)
            conn.commit()
            return result

    def log_event(self, user_id: int, event_type: str, payload: dict[str, Any] | None = None) -> None:
        payload_json = json.dumps(payload or {}, ensure_ascii=False)
        self.execute(
            'INSERT INTO user_events (user_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?)',
            (user_id, event_type, payload_json, time.time()),
        )

    def ensure_user(self, user_id: int, username: str | None = None, starter_xp: int = 0) -> None:
        now = time.time()

        def _tx(conn: sqlite3.Connection) -> None:
            row = conn.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,)).fetchone()
            safe_username = username or f'User{user_id}'
            if row:
                conn.execute('UPDATE users SET username = ?, updated_at = ? WHERE user_id = ?', (safe_username, now, user_id))
            else:
                conn.execute(
                    '''
                    INSERT INTO users (user_id, username, xp, last_daily, last_collect, daily_streak, created_at, updated_at)
                    VALUES (?, ?, ?, 0, 0, 0, ?, ?)
                    ''',
                    (user_id, safe_username, starter_xp, now, now),
                )
            stats = conn.execute('SELECT user_id FROM user_stats WHERE user_id = ?', (user_id,)).fetchone()
            if not stats:
                conn.execute(
                    'INSERT INTO user_stats (user_id, xp, level, coins, gems) VALUES (?, ?, 1, ?, 0)',
                    (user_id, 0, 1000),
                )
            rating = conn.execute('SELECT user_id FROM user_ratings WHERE user_id = ?', (user_id,)).fetchone()
            if not rating:
                conn.execute(
                    'INSERT INTO user_ratings (user_id, rating, wins, losses, streak, best_streak, updated_at) VALUES (?, 1000, 0, 0, 0, 0, ?)',
                    (user_id, now),
                )

        self.transaction(_tx)

    def get_user(self, user_id: int) -> sqlite3.Row | None:
        return self.fetchone('SELECT * FROM users WHERE user_id = ?', (user_id,))

    def get_user_xp(self, user_id: int) -> int:
        row = self.get_user(user_id)
        return int(row['xp']) if row else 0

    def add_xp(self, user_id: int, amount: int) -> None:
        self.execute('UPDATE users SET xp = xp + ?, updated_at = ? WHERE user_id = ?', (amount, time.time(), user_id))

    def spend_xp(self, user_id: int, amount: int) -> bool:
        def _tx(conn: sqlite3.Connection) -> bool:
            row = conn.execute('SELECT xp FROM users WHERE user_id = ?', (user_id,)).fetchone()
            if not row or int(row['xp']) < amount:
                return False
            conn.execute('UPDATE users SET xp = xp - ?, updated_at = ? WHERE user_id = ?', (amount, time.time(), user_id))
            return True

        return bool(self.transaction(_tx))

    def set_last_collect(self, user_id: int, timestamp: float) -> None:
        self.execute('UPDATE users SET last_collect = ?, updated_at = ? WHERE user_id = ?', (timestamp, timestamp, user_id))

    def set_daily_state(self, user_id: int, timestamp: float, streak: int) -> None:
        self.execute('UPDATE users SET last_daily = ?, daily_streak = ?, updated_at = ? WHERE user_id = ?', (timestamp, streak, timestamp, user_id))

    def add_card(self, user_id: int, name: str, artist: str, rarity: str, acquired_from: str = 'unknown') -> int:
        def _tx(conn: sqlite3.Connection) -> int:
            cur = conn.execute(
                'INSERT INTO user_cards (user_id, name, artist, rarity, acquired_from, created_at) VALUES (?, ?, ?, ?, ?, ?)',
                (user_id, name, artist, rarity, acquired_from, time.time()),
            )
            return int(cur.lastrowid)

        return int(self.transaction(_tx))

    def get_user_cards_count(self, user_id: int) -> int:
        row = self.fetchone('SELECT COUNT(*) AS count FROM user_cards WHERE user_id = ?', (user_id,))
        return int(row['count']) if row else 0

    def get_user_cards_by_rarity(self, user_id: int, rarity: str) -> list[sqlite3.Row]:
        return self.fetchall(
            'SELECT id, name, artist, rarity, acquired_from, created_at FROM user_cards WHERE user_id = ? AND rarity = ? ORDER BY id ASC',
            (user_id, rarity),
        )

    def get_user_card(self, user_id: int, card_id: int) -> sqlite3.Row | None:
        return self.fetchone(
            'SELECT id, name, artist, rarity, acquired_from, created_at FROM user_cards WHERE id = ? AND user_id = ?',
            (card_id, user_id),
        )

    def get_any_user_card(self, card_id: int) -> sqlite3.Row | None:
        return self.fetchone('SELECT id, user_id, name, artist, rarity, acquired_from, created_at FROM user_cards WHERE id = ?', (card_id,))

    def count_card_duplicates(self, user_id: int, artist: str, name: str) -> int:
        row = self.fetchone(
            'SELECT COUNT(*) AS count FROM user_cards WHERE user_id = ? AND artist = ? AND name = ?',
            (user_id, artist, name),
        )
        return int(row['count']) if row else 0

    def delete_user_cards(self, user_id: int, card_ids: list[int]) -> None:
        if not card_ids:
            return
        placeholders = ','.join('?' for _ in card_ids)
        self.execute(f'DELETE FROM user_cards WHERE user_id = ? AND id IN ({placeholders})', (user_id, *card_ids))

    def get_top_users(self, limit: int = 10) -> list[sqlite3.Row]:
        return self.fetchall(
            '''
            SELECT u.user_id, u.username, u.xp, COUNT(c.id) AS cards_count
            FROM users u
            LEFT JOIN user_cards c ON c.user_id = u.user_id
            GROUP BY u.user_id, u.username, u.xp
            ORDER BY u.xp DESC, cards_count DESC, u.user_id ASC
            LIMIT ?
            ''',
            (limit,),
        )

    def get_user_id_by_username(self, username: str) -> int | None:
        row = self.fetchone('SELECT user_id FROM users WHERE lower(username) = lower(?)', (username,))
        return int(row['user_id']) if row else None

    def get_rarity_counts(self, user_id: int) -> dict[str, int]:
        rows = self.fetchall('SELECT rarity, COUNT(*) AS count FROM user_cards WHERE user_id = ? GROUP BY rarity', (user_id,))
        return {str(row['rarity']): int(row['count']) for row in rows}

    def create_trade_offer(self, sender_id: int, recipient_id: int, card_id: int) -> int | None:
        def _tx(conn: sqlite3.Connection) -> int | None:
            card = conn.execute('SELECT id FROM user_cards WHERE id = ? AND user_id = ?', (card_id, sender_id)).fetchone()
            if not card:
                return None
            pending = conn.execute('SELECT id FROM trade_offers WHERE card_id = ? AND status = ?', (card_id, 'pending')).fetchone()
            market = conn.execute('SELECT id FROM market_listings WHERE card_id = ? AND status = ?', (card_id, 'active')).fetchone()
            auction = conn.execute('SELECT id FROM auctions WHERE card_id = ? AND status = ?', (card_id, 'active')).fetchone()
            if pending or market or auction:
                return None
            cur = conn.execute(
                'INSERT INTO trade_offers (sender_id, recipient_id, card_id, status, created_at) VALUES (?, ?, ?, ?, ?)',
                (sender_id, recipient_id, card_id, 'pending', time.time()),
            )
            return int(cur.lastrowid)

        return self.transaction(_tx)

    def get_trade_offer(self, offer_id: int) -> sqlite3.Row | None:
        return self.fetchone('SELECT * FROM trade_offers WHERE id = ?', (offer_id,))

    def resolve_trade_offer(self, offer_id: int, accept: bool) -> tuple[bool, sqlite3.Row | None]:
        def _tx(conn: sqlite3.Connection) -> tuple[bool, sqlite3.Row | None]:
            offer = conn.execute('SELECT * FROM trade_offers WHERE id = ?', (offer_id,)).fetchone()
            if not offer or offer['status'] != 'pending':
                return False, None
            if not accept:
                conn.execute('UPDATE trade_offers SET status = ?, responded_at = ? WHERE id = ?', ('declined', time.time(), offer_id))
                return True, offer
            card = conn.execute('SELECT id FROM user_cards WHERE id = ? AND user_id = ?', (offer['card_id'], offer['sender_id'])).fetchone()
            if not card:
                conn.execute('UPDATE trade_offers SET status = ?, responded_at = ? WHERE id = ?', ('expired', time.time(), offer_id))
                return False, offer
            conn.execute('UPDATE user_cards SET user_id = ? WHERE id = ?', (offer['recipient_id'], offer['card_id']))
            conn.execute('UPDATE trade_offers SET status = ?, responded_at = ? WHERE id = ?', ('accepted', time.time(), offer_id))
            return True, offer

        return self.transaction(_tx)

    def get_recent_events(self, user_id: int, limit: int = 10) -> list[sqlite3.Row]:
        return self.fetchall(
            'SELECT event_type, payload_json, created_at FROM user_events WHERE user_id = ? ORDER BY id DESC LIMIT ?',
            (user_id, limit),
        )

    # --- social / economy helpers ---
    def get_stats(self, user_id: int) -> sqlite3.Row:
        row = self.fetchone('SELECT * FROM user_stats WHERE user_id = ?', (user_id,))
        if row:
            return row
        self.ensure_user(user_id)
        return self.fetchone('SELECT * FROM user_stats WHERE user_id = ?', (user_id,))

    def add_coins(self, user_id: int, amount: int) -> None:
        self.execute('UPDATE user_stats SET coins = coins + ? WHERE user_id = ?', (amount, user_id))

    def spend_coins(self, user_id: int, amount: int) -> bool:
        def _tx(conn: sqlite3.Connection) -> bool:
            row = conn.execute('SELECT coins FROM user_stats WHERE user_id = ?', (user_id,)).fetchone()
            if not row or int(row['coins']) < amount:
                return False
            conn.execute('UPDATE user_stats SET coins = coins - ? WHERE user_id = ?', (amount, user_id))
            return True

        return bool(self.transaction(_tx))

    def add_gems(self, user_id: int, amount: int) -> None:
        self.execute('UPDATE user_stats SET gems = gems + ? WHERE user_id = ?', (amount, user_id))

    def get_battle_stats(self, user_id: int) -> dict[str, int]:
        wins = self.fetchone('SELECT COUNT(*) AS count FROM battles WHERE winner_id = ?', (user_id,))
        losses = self.fetchone('SELECT COUNT(*) AS count FROM battles WHERE loser_id = ?', (user_id,))
        return {'wins': int(wins['count']) if wins else 0, 'losses': int(losses['count']) if losses else 0}

    def record_battle(
        self,
        attacker_id: int,
        defender_id: int,
        winner_id: int,
        loser_id: int,
        attacker_score: int,
        defender_score: int,
        mode: str = 'pvp',
    ) -> None:
        self.execute(
            '''
            INSERT INTO battles (attacker_id, defender_id, winner_id, loser_id, attacker_score, defender_score, mode, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (attacker_id, defender_id, winner_id, loser_id, attacker_score, defender_score, mode, time.time()),
        )

    def get_recent_battles(self, user_id: int, limit: int = 5) -> list[sqlite3.Row]:
        return self.fetchall(
            '''
            SELECT * FROM battles
            WHERE attacker_id = ? OR defender_id = ?
            ORDER BY id DESC
            LIMIT ?
            ''',
            (user_id, user_id, limit),
        )

    def get_user_clan(self, user_id: int) -> sqlite3.Row | None:
        return self.fetchone(
            '''
            SELECT c.*, cm.role
            FROM clan_members cm
            JOIN clans c ON c.id = cm.clan_id
            WHERE cm.user_id = ?
            ''',
            (user_id,),
        )

    def list_clans(self, limit: int = 8) -> list[sqlite3.Row]:
        return self.fetchall(
            '''
            SELECT c.id, c.tag, c.name, c.owner_id, c.xp, COUNT(cm.user_id) AS members_count
            FROM clans c
            LEFT JOIN clan_members cm ON cm.clan_id = c.id
            GROUP BY c.id, c.tag, c.name, c.owner_id, c.xp
            ORDER BY c.xp DESC, members_count DESC, c.id ASC
            LIMIT ?
            ''',
            (limit,),
        )

    def create_clan(self, owner_id: int, tag: str, name: str) -> tuple[bool, str]:
        tag = tag.strip().upper()[:10]
        name = name.strip()[:32]
        if not tag or not name:
            return False, 'Некорректный тег или название.'

        def _tx(conn: sqlite3.Connection) -> tuple[bool, str]:
            existing = conn.execute('SELECT clan_id FROM clan_members WHERE user_id = ?', (owner_id,)).fetchone()
            if existing:
                return False, 'Ты уже состоишь в клане.'
            duplicate = conn.execute('SELECT id FROM clans WHERE tag = ?', (tag,)).fetchone()
            if duplicate:
                return False, 'Такой тег уже занят.'
            cur = conn.execute(
                'INSERT INTO clans (tag, name, owner_id, xp, created_at) VALUES (?, ?, ?, 0, ?)',
                (tag, name, owner_id, time.time()),
            )
            clan_id = int(cur.lastrowid)
            conn.execute(
                'INSERT INTO clan_members (clan_id, user_id, role, joined_at) VALUES (?, ?, ?, ?)',
                (clan_id, owner_id, 'owner', time.time()),
            )
            return True, 'Клан создан!'

        return self.transaction(_tx)

    def join_clan(self, user_id: int, clan_id: int) -> tuple[bool, str]:
        def _tx(conn: sqlite3.Connection) -> tuple[bool, str]:
            current = conn.execute('SELECT clan_id FROM clan_members WHERE user_id = ?', (user_id,)).fetchone()
            if current:
                return False, 'Ты уже состоишь в клане.'
            clan = conn.execute('SELECT id FROM clans WHERE id = ?', (clan_id,)).fetchone()
            if not clan:
                return False, 'Клан не найден.'
            conn.execute(
                'INSERT INTO clan_members (clan_id, user_id, role, joined_at) VALUES (?, ?, ?, ?)',
                (clan_id, user_id, 'member', time.time()),
            )
            return True, 'Ты вступил в клан.'

        return self.transaction(_tx)

    def leave_clan(self, user_id: int) -> tuple[bool, str]:
        def _tx(conn: sqlite3.Connection) -> tuple[bool, str]:
            membership = conn.execute('SELECT clan_id, role FROM clan_members WHERE user_id = ?', (user_id,)).fetchone()
            if not membership:
                return False, 'Ты не состоишь в клане.'
            clan_id = int(membership['clan_id'])
            if membership['role'] == 'owner':
                members = conn.execute('SELECT COUNT(*) AS count FROM clan_members WHERE clan_id = ?', (clan_id,)).fetchone()
                if members and int(members['count']) > 1:
                    return False, 'Владелец не может выйти, пока в клане есть другие участники.'
                conn.execute('DELETE FROM clans WHERE id = ?', (clan_id,))
                return True, 'Клан удалён.'
            conn.execute('DELETE FROM clan_members WHERE clan_id = ? AND user_id = ?', (clan_id, user_id))
            return True, 'Ты вышел из клана.'

        return self.transaction(_tx)

    def add_clan_xp(self, clan_id: int, amount: int) -> None:
        self.execute('UPDATE clans SET xp = xp + ? WHERE id = ?', (amount, clan_id))


    def get_battle_profile(self, user_id: int) -> sqlite3.Row:
        row = self.fetchone('SELECT * FROM user_ratings WHERE user_id = ?', (user_id,))
        if row:
            return row
        self.ensure_user(user_id)
        row = self.fetchone('SELECT * FROM user_ratings WHERE user_id = ?', (user_id,))
        assert row is not None
        return row

    def get_battle_leaderboard(self, limit: int = 10) -> list[sqlite3.Row]:
        return self.fetchall(
            '''
            SELECT ur.user_id, ur.rating, ur.wins, ur.losses, u.username
            FROM user_ratings ur
            JOIN users u ON u.user_id = ur.user_id
            ORDER BY ur.rating DESC, ur.wins DESC, ur.user_id ASC
            LIMIT ?
            ''',
            (limit,),
        )

    def get_deck(self, user_id: int) -> list[sqlite3.Row]:
        return self.fetchall(
            '''
            SELECT d.slot, c.id, c.name, c.artist, c.rarity
            FROM user_decks d
            JOIN user_cards c ON c.id = d.card_id
            WHERE d.user_id = ?
            ORDER BY d.slot ASC
            ''',
            (user_id,),
        )

    def clear_deck(self, user_id: int) -> None:
        self.execute('DELETE FROM user_decks WHERE user_id = ?', (user_id,))

    def save_deck(self, user_id: int, card_ids: list[int]) -> tuple[bool, str]:
        clean_ids: list[int] = []
        seen: set[int] = set()
        for card_id in card_ids:
            if card_id not in seen:
                seen.add(card_id)
                clean_ids.append(int(card_id))
        if len(clean_ids) != 5:
            return False, 'В колоде должно быть ровно 5 уникальных карт.'

        def _tx(conn: sqlite3.Connection) -> tuple[bool, str]:
            rows = conn.execute(
                f"SELECT id FROM user_cards WHERE user_id = ? AND id IN ({','.join('?' for _ in clean_ids)})",
                (user_id, *clean_ids),
            ).fetchall()
            if len(rows) != 5:
                return False, 'Не все карты принадлежат игроку.'
            conn.execute('DELETE FROM user_decks WHERE user_id = ?', (user_id,))
            for slot, card_id in enumerate(clean_ids, start=1):
                conn.execute('INSERT INTO user_decks (user_id, slot, card_id) VALUES (?, ?, ?)', (user_id, slot, card_id))
            return True, 'Колода сохранена.'

        return self.transaction(_tx)

    def auto_build_deck(self, user_id: int) -> tuple[bool, str]:
        cards = self.fetchall(
            '''
            SELECT id, rarity, created_at
            FROM user_cards
            WHERE user_id = ?
            ORDER BY CASE rarity WHEN 'limited edition' THEN 3 WHEN 'album' THEN 2 ELSE 1 END DESC, created_at DESC, id DESC
            LIMIT 5
            ''',
            (user_id,),
        )
        if len(cards) < 5:
            return False, 'Для колоды нужно минимум 5 карт.'
        return self.save_deck(user_id, [int(row['id']) for row in cards])

    def update_battle_rating(self, user_id: int, won: bool, delta: int) -> None:
        now = time.time()
        delta = int(delta)

        def _tx(conn: sqlite3.Connection) -> None:
            row = conn.execute('SELECT rating, wins, losses, streak, best_streak FROM user_ratings WHERE user_id = ?', (user_id,)).fetchone()
            if not row:
                conn.execute(
                    'INSERT INTO user_ratings (user_id, rating, wins, losses, streak, best_streak, updated_at) VALUES (?, 1000, 0, 0, 0, 0, ?)',
                    (user_id, now),
                )
                row = conn.execute('SELECT rating, wins, losses, streak, best_streak FROM user_ratings WHERE user_id = ?', (user_id,)).fetchone()
            rating = max(100, int(row['rating']) + delta)
            wins = int(row['wins']) + (1 if won else 0)
            losses = int(row['losses']) + (0 if won else 1)
            streak = int(row['streak']) + 1 if won else 0
            best_streak = max(int(row['best_streak']), streak)
            conn.execute(
                'UPDATE user_ratings SET rating = ?, wins = ?, losses = ?, streak = ?, best_streak = ?, updated_at = ? WHERE user_id = ?',
                (rating, wins, losses, streak, best_streak, now, user_id),
            )

        self.transaction(_tx)

    def get_recent_battles_detailed(self, user_id: int, limit: int = 10) -> list[sqlite3.Row]:
        return self.fetchall(
            '''
            SELECT b.*, ua.username AS attacker_username, ud.username AS defender_username
            FROM battles b
            JOIN users ua ON ua.user_id = b.attacker_id
            JOIN users ud ON ud.user_id = b.defender_id
            WHERE b.attacker_id = ? OR b.defender_id = ?
            ORDER BY b.id DESC
            LIMIT ?
            ''',
            (user_id, user_id, limit),
        )

    def get_market_listing(self, listing_id: int) -> sqlite3.Row | None:
        return self.fetchone(
            '''
            SELECT ml.*, uc.name, uc.artist, uc.rarity
            FROM market_listings ml
            JOIN user_cards uc ON uc.id = ml.card_id
            WHERE ml.id = ?
            ''',
            (listing_id,),
        )

    def list_market_listings(self, limit: int = 8) -> list[sqlite3.Row]:
        return self.fetchall(
            '''
            SELECT ml.id, ml.seller_id, ml.card_id, ml.price, ml.created_at, uc.name, uc.artist, uc.rarity
            FROM market_listings ml
            JOIN user_cards uc ON uc.id = ml.card_id
            WHERE ml.status = 'active'
            ORDER BY ml.id DESC
            LIMIT ?
            ''',
            (limit,),
        )

    def create_market_listing(self, seller_id: int, card_id: int, price: int) -> tuple[bool, str]:
        if price <= 0:
            return False, 'Цена должна быть больше нуля.'

        def _tx(conn: sqlite3.Connection) -> tuple[bool, str]:
            card = conn.execute('SELECT id FROM user_cards WHERE id = ? AND user_id = ?', (card_id, seller_id)).fetchone()
            if not card:
                return False, 'Карта не найдена.'
            if conn.execute("SELECT id FROM trade_offers WHERE card_id = ? AND status = 'pending'", (card_id,)).fetchone():
                return False, 'Карта уже участвует в обмене.'
            if conn.execute("SELECT id FROM auctions WHERE card_id = ? AND status = 'active'", (card_id,)).fetchone():
                return False, 'Карта уже участвует в аукционе.'
            if conn.execute("SELECT id FROM market_listings WHERE card_id = ? AND status = 'active'", (card_id,)).fetchone():
                return False, 'Карта уже выставлена на рынок.'
            conn.execute(
                '''
                INSERT INTO market_listings (seller_id, card_id, price, status, created_at)
                VALUES (?, ?, ?, 'active', ?)
                ''',
                (seller_id, card_id, price, time.time()),
            )
            return True, 'Лот выставлен на рынок.'

        return self.transaction(_tx)

    def buy_market_listing(self, buyer_id: int, listing_id: int) -> tuple[bool, str]:
        def _tx(conn: sqlite3.Connection) -> tuple[bool, str]:
            listing = conn.execute(
                'SELECT * FROM market_listings WHERE id = ? AND status = ?',
                (listing_id, 'active'),
            ).fetchone()
            if not listing:
                return False, 'Лот уже недоступен.'
            if int(listing['seller_id']) == buyer_id:
                return False, 'Нельзя купить свой же лот.'
            buyer = conn.execute('SELECT coins FROM user_stats WHERE user_id = ?', (buyer_id,)).fetchone()
            if not buyer or int(buyer['coins']) < int(listing['price']):
                return False, 'Недостаточно coins.'
            card = conn.execute('SELECT user_id FROM user_cards WHERE id = ?', (listing['card_id'],)).fetchone()
            if not card or int(card['user_id']) != int(listing['seller_id']):
                conn.execute('UPDATE market_listings SET status = ? WHERE id = ?', ('expired', listing_id))
                return False, 'Карта недоступна.'
            conn.execute('UPDATE user_stats SET coins = coins - ? WHERE user_id = ?', (listing['price'], buyer_id))
            conn.execute('UPDATE user_stats SET coins = coins + ? WHERE user_id = ?', (listing['price'], listing['seller_id']))
            conn.execute('UPDATE user_cards SET user_id = ? WHERE id = ?', (buyer_id, listing['card_id']))
            conn.execute(
                'UPDATE market_listings SET buyer_id = ?, status = ?, sold_at = ? WHERE id = ?',
                (buyer_id, 'sold', time.time(), listing_id),
            )
            return True, 'Покупка завершена.'

        return self.transaction(_tx)

    def create_auction(self, seller_id: int, card_id: int, start_price: int, duration_hours: int = 12) -> tuple[bool, str]:
        if start_price <= 0:
            return False, 'Стартовая цена должна быть больше нуля.'
        ends_at = time.time() + max(1, duration_hours) * 3600

        def _tx(conn: sqlite3.Connection) -> tuple[bool, str]:
            card = conn.execute('SELECT id FROM user_cards WHERE id = ? AND user_id = ?', (card_id, seller_id)).fetchone()
            if not card:
                return False, 'Карта не найдена.'
            if conn.execute("SELECT id FROM trade_offers WHERE card_id = ? AND status = 'pending'", (card_id,)).fetchone():
                return False, 'Карта уже участвует в обмене.'
            if conn.execute("SELECT id FROM market_listings WHERE card_id = ? AND status = 'active'", (card_id,)).fetchone():
                return False, 'Карта уже выставлена на рынок.'
            if conn.execute("SELECT id FROM auctions WHERE card_id = ? AND status = 'active'", (card_id,)).fetchone():
                return False, 'Карта уже участвует в аукционе.'
            conn.execute(
                '''
                INSERT INTO auctions (seller_id, card_id, start_price, current_price, highest_bidder_id, status, ends_at, created_at)
                VALUES (?, ?, ?, ?, NULL, 'active', ?, ?)
                ''',
                (seller_id, card_id, start_price, start_price, ends_at, time.time()),
            )
            return True, 'Аукцион запущен.'

        return self.transaction(_tx)

    def resolve_expired_auctions(self) -> None:
        now = time.time()

        def _tx(conn: sqlite3.Connection) -> None:
            rows = conn.execute("SELECT * FROM auctions WHERE status = 'active' AND ends_at <= ?", (now,)).fetchall()
            for auction in rows:
                if auction['highest_bidder_id']:
                    card = conn.execute('SELECT user_id FROM user_cards WHERE id = ?', (auction['card_id'],)).fetchone()
                    if card and int(card['user_id']) == int(auction['seller_id']):
                        conn.execute('UPDATE user_cards SET user_id = ? WHERE id = ?', (auction['highest_bidder_id'], auction['card_id']))
                        conn.execute('UPDATE user_stats SET coins = coins + ? WHERE user_id = ?', (auction['current_price'], auction['seller_id']))
                        conn.execute(
                            "UPDATE auctions SET status = 'finished', resolved_at = ? WHERE id = ?",
                            (now, auction['id']),
                        )
                    else:
                        conn.execute("UPDATE auctions SET status = 'cancelled', resolved_at = ? WHERE id = ?", (now, auction['id']))
                else:
                    conn.execute("UPDATE auctions SET status = 'expired', resolved_at = ? WHERE id = ?", (now, auction['id']))

        self.transaction(_tx)

    def list_auctions(self, limit: int = 8) -> list[sqlite3.Row]:
        self.resolve_expired_auctions()
        return self.fetchall(
            '''
            SELECT a.id, a.seller_id, a.card_id, a.start_price, a.current_price, a.highest_bidder_id, a.ends_at, uc.artist, uc.name, uc.rarity
            FROM auctions a
            JOIN user_cards uc ON uc.id = a.card_id
            WHERE a.status = 'active'
            ORDER BY a.ends_at ASC, a.id ASC
            LIMIT ?
            ''',
            (limit,),
        )

    def get_auction(self, auction_id: int) -> sqlite3.Row | None:
        self.resolve_expired_auctions()
        return self.fetchone(
            '''
            SELECT a.*, uc.artist, uc.name, uc.rarity
            FROM auctions a
            JOIN user_cards uc ON uc.id = a.card_id
            WHERE a.id = ?
            ''',
            (auction_id,),
        )

    def place_bid(self, bidder_id: int, auction_id: int, amount: int) -> tuple[bool, str]:
        now = time.time()

        def _tx(conn: sqlite3.Connection) -> tuple[bool, str]:
            auction = conn.execute('SELECT * FROM auctions WHERE id = ?', (auction_id,)).fetchone()
            if not auction or auction['status'] != 'active':
                return False, 'Аукцион недоступен.'
            if float(auction['ends_at']) <= now:
                return False, 'Аукцион уже завершился.'
            if int(auction['seller_id']) == bidder_id:
                return False, 'Нельзя ставить на свой аукцион.'
            min_bid = int(auction['current_price']) + 100
            if amount < min_bid:
                return False, f'Минимальная ставка: {min_bid} coins.'
            bidder = conn.execute('SELECT coins FROM user_stats WHERE user_id = ?', (bidder_id,)).fetchone()
            if not bidder or int(bidder['coins']) < amount:
                return False, 'Недостаточно coins.'
            if auction['highest_bidder_id']:
                conn.execute('UPDATE user_stats SET coins = coins + ? WHERE user_id = ?', (auction['current_price'], auction['highest_bidder_id']))
            conn.execute('UPDATE user_stats SET coins = coins - ? WHERE user_id = ?', (amount, bidder_id))
            conn.execute(
                'UPDATE auctions SET current_price = ?, highest_bidder_id = ? WHERE id = ?',
                (amount, bidder_id, auction_id),
            )
            return True, 'Ставка принята.'

        return self.transaction(_tx)
