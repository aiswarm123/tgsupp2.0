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
    if row is None:
        return None
    return {"id": row[0], "telegram_group_id": row[1], "topic_count": row[2]}


async def register_group(db: aiosqlite.Connection, telegram_group_id: int) -> int:
    cur = await db.execute(
        "INSERT OR IGNORE INTO admin_groups (telegram_group_id) VALUES (?)",
        (telegram_group_id,),
    )
    await db.commit()
    return cur.lastrowid


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


async def get_all_active_group_ids(db: aiosqlite.Connection) -> list[int]:
    async with db.execute(
        "SELECT telegram_group_id FROM admin_groups WHERE is_active = 1"
    ) as cur:
        rows = await cur.fetchall()
    return [r[0] for r in rows]


# ── Users ─────────────────────────────────────────────────────────────────────

async def get_user(db: aiosqlite.Connection, telegram_id: int) -> Optional[dict]:
    async with db.execute(
        "SELECT id, telegram_id, language, group_id, topic_id FROM users WHERE telegram_id = ?",
        (telegram_id,),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "telegram_id": row[1],
        "language": row[2],
        "group_id": row[3],
        "topic_id": row[4],
    }


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
    if row is None:
        return None
    return {"id": row[0], "status": row[1], "ai_enabled": bool(row[2])}


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


async def get_conversation_by_id(
    db: aiosqlite.Connection, conversation_id: int
) -> Optional[dict]:
    async with db.execute(
        "SELECT id, user_id, status, ai_enabled FROM conversations WHERE id = ?",
        (conversation_id,),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return None
    return {"id": row[0], "user_id": row[1], "status": row[2], "ai_enabled": bool(row[3])}


# ── Messages ──────────────────────────────────────────────────────────────────

async def save_message(
    db: aiosqlite.Connection, conversation_id: int, role: str, text: str
) -> None:
    await db.execute(
        "INSERT INTO messages (conversation_id, role, text) VALUES (?, ?, ?)",
        (conversation_id, role, text),
    )
    await db.commit()


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
        ai_role = "assistant" if role in ("ai", "agent") else "user"
        result.append({"role": ai_role, "content": text})
    return result
