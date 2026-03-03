import aiosqlite


_CREATE_ADMIN_GROUPS = """
CREATE TABLE IF NOT EXISTS admin_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_group_id INTEGER UNIQUE NOT NULL,
    topic_count INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT 1,
    registered_at DATETIME NOT NULL
)
"""

_CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE NOT NULL,
    language TEXT DEFAULT 'en',
    first_seen DATETIME NOT NULL,
    group_id INTEGER REFERENCES admin_groups(id),
    topic_id INTEGER
)
"""

_CREATE_CONVERSATIONS = """
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    status TEXT DEFAULT 'ai',
    ai_enabled BOOLEAN DEFAULT 1,
    created_at DATETIME NOT NULL,
    closed_at DATETIME,
    closed_by INTEGER
)
"""

_CREATE_MESSAGES = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id),
    role TEXT NOT NULL,
    text TEXT NOT NULL,
    timestamp DATETIME NOT NULL
)
"""


async def init_db(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(_CREATE_ADMIN_GROUPS)
        await db.execute(_CREATE_USERS)
        await db.execute(_CREATE_CONVERSATIONS)
        await db.execute(_CREATE_MESSAGES)
        await db.commit()
