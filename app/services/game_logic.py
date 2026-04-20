from __future__ import annotations

import random
from collections import Counter
from typing import Any

from app.data import CARD_POOL, PACKS, RARITY_ORDER, RARITY_WEIGHTS, XP_VALUES


def get_rarity() -> str:
    roll = random.randint(1, 100)
    threshold = 0
    for rarity, weight in RARITY_WEIGHTS:
        threshold += weight
        if roll <= threshold:
            return rarity
    return 'single'


def random_card(rarity: str | None = None) -> dict[str, Any]:
    chosen_rarity = rarity or get_rarity()
    card = random.choice(CARD_POOL[chosen_rarity]).copy()
    card['rarity'] = chosen_rarity
    return card


def xp_for_rarity(rarity: str) -> int:
    return XP_VALUES[rarity]


def daily_xp_reward(streak: int) -> int:
    bonus = min(150, streak * 10)
    return random.randint(50, 120) + bonus


def build_pack(pack_key: str) -> list[dict[str, Any]]:
    pack = PACKS[pack_key]
    count = int(pack['cards_count'])
    guaranteed = str(pack['guaranteed'])
    opened = [random_card() for _ in range(max(0, count - 1))]
    opened.append(random_card(guaranteed))
    random.shuffle(opened)
    return opened


def summarise_rarities(cards: list[dict[str, Any]]) -> dict[str, int]:
    counter = Counter(card['rarity'] for card in cards)
    return {rarity: counter.get(rarity, 0) for rarity in RARITY_ORDER}
