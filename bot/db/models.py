import sqlite3

import aiosqlite


CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE NOT NULL,
    language TEXT NOT NULL DEFAULT 'en',
    first_seen DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    group_id INTEGER REFERENCES admin_groups(id),
    topic_id INTEGER
)
"""

CREATE_ADMIN_GROUPS = """
CREATE TABLE IF NOT EXISTS admin_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_group_id INTEGER UNIQUE NOT NULL,
    topic_count INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    registered_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

CREATE_CONVERSATIONS = """
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'ai',
    ai_enabled BOOLEAN NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    closed_at DATETIME,
    closed_by INTEGER
)
"""

CREATE_MESSAGES = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id),
    role TEXT NOT NULL,
    text TEXT NOT NULL,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sender_id INTEGER
)
"""

CREATE_FAQ_ITEMS = """
CREATE TABLE IF NOT EXISTS faq_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    media_file_id TEXT,
    position INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

_INDICES = [
    "CREATE INDEX IF NOT EXISTS idx_users_topic_id ON users(topic_id)",
    "CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id)",
]


async def init_db(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(CREATE_ADMIN_GROUPS)
        await db.execute(CREATE_USERS)
        await db.execute(CREATE_CONVERSATIONS)
        await db.execute(CREATE_MESSAGES)
        await db.execute(CREATE_FAQ_ITEMS)
        for idx_sql in _INDICES:
            await db.execute(idx_sql)
        # Migration: add sender_id to existing databases
        try:
            await db.execute("ALTER TABLE messages ADD COLUMN sender_id INTEGER")
        except sqlite3.OperationalError:
            pass  # Column already exists
        await db.commit()
