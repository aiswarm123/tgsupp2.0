from datetime import datetime
from typing import Optional

import aiosqlite


def _row_to_dict(cursor: aiosqlite.Cursor, row: tuple) -> dict:
    return dict(zip([d[0] for d in cursor.description], row))


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

async def get_user_by_telegram_id(db: aiosqlite.Connection, telegram_id: int) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
    ) as cursor:
        row = await cursor.fetchone()
        return _row_to_dict(cursor, row) if row else None


async def get_user_by_topic(
    db: aiosqlite.Connection, group_telegram_id: int, topic_id: int
) -> Optional[dict]:
    async with db.execute(
        "SELECT u.* FROM users u "
        "JOIN admin_groups ag ON u.group_id = ag.id "
        "WHERE ag.telegram_group_id = ? AND u.topic_id = ?",
        (group_telegram_id, topic_id),
    ) as cursor:
        row = await cursor.fetchone()
        return _row_to_dict(cursor, row) if row else None


async def create_user(
    db: aiosqlite.Connection,
    telegram_id: int,
    language: str,
    group_id: Optional[int],
    topic_id: Optional[int],
) -> int:
    cursor = await db.execute(
        "INSERT INTO users (telegram_id, language, first_seen, group_id, topic_id) "
        "VALUES (?, ?, ?, ?, ?)",
        (telegram_id, language, datetime.utcnow().isoformat(), group_id, topic_id),
    )
    await db.commit()
    return cursor.lastrowid


async def update_user_topic(
    db: aiosqlite.Connection, user_id: int, group_id: int, topic_id: int
) -> None:
    await db.execute(
        "UPDATE users SET group_id = ?, topic_id = ? WHERE id = ?",
        (group_id, topic_id, user_id),
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Admin groups
# ---------------------------------------------------------------------------

async def get_active_admin_group(db: aiosqlite.Connection) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM admin_groups WHERE is_active = 1 ORDER BY id DESC LIMIT 1"
    ) as cursor:
        row = await cursor.fetchone()
        return _row_to_dict(cursor, row) if row else None


async def get_admin_group_by_telegram_id(
    db: aiosqlite.Connection, telegram_group_id: int
) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM admin_groups WHERE telegram_group_id = ?", (telegram_group_id,)
    ) as cursor:
        row = await cursor.fetchone()
        return _row_to_dict(cursor, row) if row else None


async def register_admin_group(
    db: aiosqlite.Connection, telegram_group_id: int
) -> tuple[int, bool]:
    """Register a group. Returns (group_id, is_new). is_new=False means already registered."""
    try:
        cursor = await db.execute(
            "INSERT INTO admin_groups (telegram_group_id, topic_count, is_active, registered_at) "
            "VALUES (?, 0, 1, ?)",
            (telegram_group_id, datetime.utcnow().isoformat()),
        )
        await db.commit()
        return cursor.lastrowid, True
    except aiosqlite.IntegrityError:
        async with db.execute(
            "SELECT id FROM admin_groups WHERE telegram_group_id = ?", (telegram_group_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0], False


async def increment_topic_count(db: aiosqlite.Connection, group_id: int) -> int:
    """Increment topic count and return the new value."""
    await db.execute(
        "UPDATE admin_groups SET topic_count = topic_count + 1 WHERE id = ?", (group_id,)
    )
    await db.commit()
    async with db.execute(
        "SELECT topic_count FROM admin_groups WHERE id = ?", (group_id,)
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else 0


async def deactivate_admin_group(db: aiosqlite.Connection, group_id: int) -> None:
    await db.execute(
        "UPDATE admin_groups SET is_active = 0 WHERE id = ?", (group_id,)
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

async def get_active_conversation(
    db: aiosqlite.Connection, user_id: int
) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM conversations WHERE user_id = ? AND status != 'closed' "
        "ORDER BY created_at DESC LIMIT 1",
        (user_id,),
    ) as cursor:
        row = await cursor.fetchone()
        return _row_to_dict(cursor, row) if row else None


async def get_conversation_by_id(
    db: aiosqlite.Connection, conv_id: int
) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM conversations WHERE id = ?", (conv_id,)
    ) as cursor:
        row = await cursor.fetchone()
        return _row_to_dict(cursor, row) if row else None


async def create_conversation(db: aiosqlite.Connection, user_id: int) -> int:
    cursor = await db.execute(
        "INSERT INTO conversations (user_id, status, ai_enabled, created_at) "
        "VALUES (?, 'ai', 1, ?)",
        (user_id, datetime.utcnow().isoformat()),
    )
    await db.commit()
    return cursor.lastrowid


async def set_ai_enabled(
    db: aiosqlite.Connection, conv_id: int, enabled: bool
) -> None:
    await db.execute(
        "UPDATE conversations SET ai_enabled = ? WHERE id = ?", (int(enabled), conv_id)
    )
    await db.commit()


async def set_conversation_status(
    db: aiosqlite.Connection,
    conv_id: int,
    status: str,
    closed_by: Optional[int] = None,
    closed_at: Optional[datetime] = None,
) -> None:
    if status == "closed":
        await db.execute(
            "UPDATE conversations SET status = ?, closed_by = ?, closed_at = ? WHERE id = ?",
            (
                status,
                closed_by,
                closed_at.isoformat() if closed_at else datetime.utcnow().isoformat(),
                conv_id,
            ),
        )
    else:
        await db.execute(
            "UPDATE conversations SET status = ? WHERE id = ?", (status, conv_id)
        )
    await db.commit()


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

async def add_message(
    db: aiosqlite.Connection,
    conv_id: int,
    role: str,
    text: str,
    sender_id: Optional[int] = None,
) -> int:
    cursor = await db.execute(
        "INSERT INTO messages (conversation_id, role, text, timestamp, sender_id) "
        "VALUES (?, ?, ?, ?, ?)",
        (conv_id, role, text, datetime.utcnow().isoformat(), sender_id),
    )
    await db.commit()
    return cursor.lastrowid


async def get_conversation_history(
    db: aiosqlite.Connection, conv_id: int
) -> list[dict]:
    async with db.execute(
        "SELECT role, text FROM messages WHERE conversation_id = ? ORDER BY timestamp",
        (conv_id,),
    ) as cursor:
        rows = await cursor.fetchall()
        result = []
        for role, text in rows:
            if role == "agent":
                result.append({"role": "user", "content": f"[Support Agent]: {text}"})
            else:
                result.append({"role": role, "content": text})
        return result


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

async def get_stats(db: aiosqlite.Connection) -> dict:
    async with db.execute(
        "SELECT COUNT(*) FROM conversations WHERE status != 'closed'"
    ) as cursor:
        open_count = (await cursor.fetchone())[0]

    async with db.execute(
        "SELECT COUNT(*) FROM conversations WHERE status = 'closed'"
    ) as cursor:
        closed_count = (await cursor.fetchone())[0]

    # Average seconds from conversation start to first agent reply
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
    ) as cursor:
        row = await cursor.fetchone()
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
    ) as cursor:
        row = await cursor.fetchone()
        active_agents = row[0] if row else 0

    return {
        "open_count": open_count,
        "closed_count": closed_count,
        "avg_response_time": avg_response_time,
        "active_agents": active_agents,
    }
