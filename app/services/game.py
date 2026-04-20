import random

def add_xp(cursor, user_id, amount):
    cursor.execute("SELECT xp FROM user_stats WHERE user_id=?", (user_id,))
    row = cursor.fetchone()

    if not row:
        cursor.execute("INSERT INTO user_stats (user_id, xp) VALUES (?, ?)", (user_id, amount))
        return

    xp = row[0] + amount
    level = xp // 100 + 1

    cursor.execute("UPDATE user_stats SET xp=?, level=? WHERE user_id=?", (xp, level, user_id))


def reward(cursor, user_id, coins=0, gems=0):
    cursor.execute("""
    INSERT INTO user_stats (user_id, coins, gems)
    VALUES (?, ?, ?)
    ON CONFLICT(user_id) DO UPDATE SET
        coins = coins + ?,
        gems = gems + ?
    """, (user_id, coins, gems, coins, gems))


def update_task(cursor, user_id, task):
    cursor.execute("""
    UPDATE daily_tasks
    SET progress = progress + 1
    WHERE user_id=? AND task=?
    """, (user_id, task))