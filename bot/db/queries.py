from __future__ import annotations

import aiosqlite
from typing import Optional


# ── Admin groups ──────────────────────────────────────────────────────────────

async def get_active_group(db: aiosqlite.Connection) -> Optional[dict]:
    """Return the active admin group with available capacity, or None."""
    async with db.execute(
        "SELECT id, telegram_group_id, topic_count FROM admin_groups "
        "WHERE is_active = 1 AND topic_count < 9500 LIMIT 1"
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def get_group_by_telegram_id(
    db: aiosqlite.Connection, telegram_group_id: int
) -> Optional[dict]:
    """Return a registered admin group by its Telegram chat ID, or None."""
    async with db.execute(
        "SELECT id, telegram_group_id, topic_count, is_active FROM admin_groups "
        "WHERE telegram_group_id = ?",
        (telegram_group_id,),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def register_group(db: aiosqlite.Connection, telegram_group_id: int) -> tuple[int, bool]:
    """Register a group. Returns (group_id, is_new). is_new=False when already registered."""
    cur = await db.execute(
        "INSERT OR IGNORE INTO admin_groups (telegram_group_id) VALUES (?)",
        (telegram_group_id,),
    )
    await db.commit()
    if cur.lastrowid:
        return cur.lastrowid, True
    # Duplicate: fetch existing id
    async with db.execute(
        "SELECT id FROM admin_groups WHERE telegram_group_id = ?", (telegram_group_id,)
    ) as cur2:
        row = await cur2.fetchone()
        return row[0], False


async def increment_topic_count(db: aiosqlite.Connection, group_id: int) -> int:
    """Increment topic_count and return new value."""
    await db.execute(
        "UPDATE admin_groups SET topic_count = topic_count + 1 WHERE id = ?",
        (group_id,),
    )
    await db.commit()
    async with db.execute(
        "SELECT topic_count FROM admin_groups WHERE id = ?", (group_id,)
    ) as cur:
        row = await cur.fetchone()
    return row[0]


async def get_group_topic_count(db: aiosqlite.Connection, group_id: int) -> int:
    async with db.execute(
        "SELECT topic_count FROM admin_groups WHERE id = ?", (group_id,)
    ) as cur:
        row = await cur.fetchone()
    return row[0] if row else 0


async def get_group_tg_id(db: aiosqlite.Connection, group_id: int) -> Optional[int]:
    """Return a group's Telegram chat ID by internal PK, or None."""
    async with db.execute(
        "SELECT telegram_group_id FROM admin_groups WHERE id = ?", (group_id,)
    ) as cur:
        row = await cur.fetchone()
    return row[0] if row else None


async def get_all_active_group_ids(db: aiosqlite.Connection) -> list[int]:
    async with db.execute(
        "SELECT telegram_group_id FROM admin_groups WHERE is_active = 1"
    ) as cur:
        rows = await cur.fetchall()
    return [r[0] for r in rows]


# ── Users ─────────────────────────────────────────────────────────────────────

_USER_COLS = "id, telegram_id, language, group_id, topic_id"


async def get_user(db: aiosqlite.Connection, telegram_id: int) -> Optional[dict]:
    async with db.execute(
        f"SELECT {_USER_COLS} FROM users WHERE telegram_id = ?",
        (telegram_id,),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def get_user_by_id(db: aiosqlite.Connection, user_id: int) -> Optional[dict]:
    """Return a user row by internal primary key."""
    async with db.execute(
        f"SELECT {_USER_COLS} FROM users WHERE id = ?",
        (user_id,),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def create_user(
    db: aiosqlite.Connection,
    telegram_id: int,
    language: str,
    group_id: int,
    topic_id: int,
) -> int:
    cur = await db.execute(
        "INSERT INTO users (telegram_id, language, group_id, topic_id) VALUES (?, ?, ?, ?)",
        (telegram_id, language, group_id, topic_id),
    )
    await db.commit()
    return cur.lastrowid


async def update_user_topic(
    db: aiosqlite.Connection, telegram_id: int, group_id: int, topic_id: int
) -> None:
    await db.execute(
        "UPDATE users SET group_id = ?, topic_id = ? WHERE telegram_id = ?",
        (group_id, topic_id, telegram_id),
    )
    await db.commit()


# ── Conversations ─────────────────────────────────────────────────────────────

async def get_open_conversation(
    db: aiosqlite.Connection, user_id: int
) -> Optional[dict]:
    async with db.execute(
        "SELECT id, status, ai_enabled FROM conversations "
        "WHERE user_id = ? AND status != 'closed' ORDER BY id DESC LIMIT 1",
        (user_id,),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def create_conversation(db: aiosqlite.Connection, user_id: int) -> int:
    cur = await db.execute(
        "INSERT INTO conversations (user_id) VALUES (?)", (user_id,)
    )
    await db.commit()
    return cur.lastrowid


async def set_ai_enabled(
    db: aiosqlite.Connection, conversation_id: int, enabled: bool
) -> None:
    await db.execute(
        "UPDATE conversations SET ai_enabled = ? WHERE id = ?",
        (int(enabled), conversation_id),
    )
    await db.commit()


async def set_conversation_status(
    db: aiosqlite.Connection, conversation_id: int, status: str, closed_by: Optional[int] = None
) -> None:
    if status == "closed":
        await db.execute(
            "UPDATE conversations SET status = ?, closed_at = CURRENT_TIMESTAMP, closed_by = ? WHERE id = ?",
            (status, closed_by, conversation_id),
        )
    else:
        await db.execute(
            "UPDATE conversations SET status = ? WHERE id = ?",
            (status, conversation_id),
        )
    await db.commit()


async def escalate_to_human(db: aiosqlite.Connection, conversation_id: int) -> None:
    """Disable AI and set status to human in a single commit."""
    await db.execute(
        "UPDATE conversations SET ai_enabled = 0, status = 'human' WHERE id = ?",
        (conversation_id,),
    )
    await db.commit()


async def get_conversation_by_id(
    db: aiosqlite.Connection, conversation_id: int
) -> Optional[dict]:
    async with db.execute(
        "SELECT id, user_id, status, ai_enabled FROM conversations WHERE id = ?",
        (conversation_id,),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def get_user_conv_by_topic(
    db: aiosqlite.Connection, group_id: int, topic_id: int
) -> Optional[tuple[int, int]]:
    """Return (telegram_id, conv_id) for an open conversation in the given group/topic."""
    async with db.execute(
        "SELECT u.telegram_id, c.id AS conv_id FROM users u "
        "JOIN conversations c ON c.user_id = u.id "
        "WHERE u.group_id = ? AND u.topic_id = ? AND c.status != 'closed' "
        "ORDER BY c.id DESC LIMIT 1",
        (group_id, topic_id),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return None
    return row[0], row[1]


# ── Messages ──────────────────────────────────────────────────────────────────

async def save_message(
    db: aiosqlite.Connection,
    conversation_id: int,
    role: str,
    text: str,
    sender_id: Optional[int] = None,
) -> None:
    await db.execute(
        "INSERT INTO messages (conversation_id, role, text, sender_id) VALUES (?, ?, ?, ?)",
        (conversation_id, role, text, sender_id),
    )
    await db.commit()


# ── Stats ──────────────────────────────────────────────────────────────────────

async def get_stats(db: aiosqlite.Connection) -> dict:
    async with db.execute(
        "SELECT COUNT(*) FROM conversations WHERE status != 'closed'"
    ) as cur:
        open_count = (await cur.fetchone())[0]

    async with db.execute(
        "SELECT COUNT(*) FROM conversations WHERE status = 'closed'"
    ) as cur:
        closed_count = (await cur.fetchone())[0]

    # Average seconds from conversation creation to first agent reply
    async with db.execute(
        """
        SELECT AVG((julianday(m.timestamp) - julianday(c.created_at)) * 86400.0)
        FROM conversations c
        JOIN messages m ON m.conversation_id = c.id
        WHERE m.role = 'agent'
          AND m.id = (
              SELECT MIN(id) FROM messages
              WHERE conversation_id = c.id AND role = 'agent'
          )
        """
    ) as cur:
        row = await cur.fetchone()
        avg_response_time = row[0] if row and row[0] is not None else None

    # Active agents: distinct sender_ids with role='agent' that replied in last 24h
    async with db.execute(
        """
        SELECT COUNT(DISTINCT sender_id)
        FROM messages
        WHERE role = 'agent'
          AND sender_id IS NOT NULL
          AND timestamp >= datetime('now', '-24 hours')
        """
    ) as cur:
        row = await cur.fetchone()
        active_agents = row[0] if row else 0

    return {
        "open_count": open_count,
        "closed_count": closed_count,
        "avg_response_time": avg_response_time,
        "active_agents": active_agents,
    }


async def get_conversation_history(
    db: aiosqlite.Connection, conversation_id: int
) -> list[dict]:
    """Return messages as list of {role, content} dicts for AI client."""
    async with db.execute(
        "SELECT role, text FROM messages WHERE conversation_id = ? ORDER BY id ASC",
        (conversation_id,),
    ) as cur:
        rows = await cur.fetchall()
    result = []
    for role, text in rows:
        # Map DB roles to AI roles
        if role == "ai":
            result.append({"role": "assistant", "content": text})
        elif role == "agent":
            result.append({"role": "user", "content": f"[Support Agent]: {text}"})
        else:
            result.append({"role": "user", "content": text})
    return result
