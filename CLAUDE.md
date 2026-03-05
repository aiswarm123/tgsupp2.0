# tgsupp2.0 — Telegram Support Bot

## Project Overview

Hybrid Telegram support bot: AI auto-replies to users, support agents can jump in at any time by replying in the admin forum group. Built with aiogram 3.x, SQLite, and a configurable AI provider (Claude by default).

## User Flow

1. User sends any message to the bot
2. Bot forwards the message to the user's topic in the admin forum group
3. AI auto-replies to the user (with full conversation history as context)
4. Support agent can reply at any time by replying to the forwarded message in the topic — bot delivers it to the user
5. Once a human agent replies, AI stops auto-replying for that conversation
6. "Talk to human 🙋" button under AI replies flags the conversation (disables AI, marks as priority in the group)
7. Agents close tickets via inline button — no notification sent to the user
8. Admins can toggle AI back on per conversation via inline button

## Admin Group Organization

- Admin groups are Telegram **forum supergroups** (topics enabled)
- Each user gets their **own topic** in the group (named by user's name/username)
- All messages from a user appear in their topic thread
- Agents reply in the thread — bot forwards reply to user
- Inline buttons in topic: `Close ✅` | `Toggle AI 🤖`

## Multi-Group Rotation

- Each forum group holds up to **9,500 users** (safe threshold before Telegram's 10k limit)
- **Warning at 80%** (7,600 topics): bot alerts all admins
- **Warning at 95%** (9,025 topics): second alert, more urgent
- When active group is full: bot stops routing new users there, waits for a new group
- Admins create a new forum supergroup, add the bot as admin, run `/register_group`
- Bot registers the group and starts routing new users to it
- Existing users always stay in their original group

## Admin Commands

- `/register_group` — register current group as an admin support group
- `/stats` — show open/closed tickets, avg response time, active agents
- `/toggle_ai <user_id>` — manually toggle AI for a user's conversation

## Tech Stack

- **Framework:** `aiogram 3.x` (async Python)
- **Database:** `SQLite` via `aiosqlite`
- **AI:** Claude API by default, configurable via `.env` (openai-compatible)
- **i18n:** JSON-based locale files, EN/RU/UA, auto-detected from Telegram language
- **Config:** `pydantic-settings` + `.env`
- **Deploy:** Docker + docker-compose
- **Dev:** agent-orchestrator (ao) with parallel agents per module

## Project Structure

```
tgsupp2.0/
├── bot/
│   ├── handlers/
│   │   ├── user.py          # incoming user messages, escalation button
│   │   └── admin.py         # admin group replies, inline callbacks, commands
│   ├── ai/
│   │   └── client.py        # AI provider abstraction (send_message)
│   ├── db/
│   │   ├── models.py        # table definitions, init_db()
│   │   └── queries.py       # all async DB queries
│   ├── middlewares/
│   │   └── i18n.py          # detect language, inject translator into handler
│   ├── keyboards/
│   │   └── inline.py        # all InlineKeyboardMarkup builders
│   ├── locales/
│   │   ├── en.json
│   │   ├── ru.json
│   │   └── ua.json
│   └── config.py            # pydantic BaseSettings
├── main.py                  # bot startup, dispatcher, middleware registration
├── .env.example
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── Makefile
```

## Database Schema

### users
| column | type | notes |
|---|---|---|
| id | INTEGER PK | |
| telegram_id | INTEGER UNIQUE | |
| language | TEXT | en/ru/ua |
| first_seen | DATETIME | |
| group_id | INTEGER FK | admin_groups.id |
| topic_id | INTEGER | Telegram topic/thread id in the group |

### admin_groups
| column | type | notes |
|---|---|---|
| id | INTEGER PK | |
| telegram_group_id | INTEGER UNIQUE | |
| topic_count | INTEGER | current number of topics |
| is_active | BOOLEAN | whether new users are routed here |
| registered_at | DATETIME | |

### conversations
| column | type | notes |
|---|---|---|
| id | INTEGER PK | |
| user_id | INTEGER FK | users.id |
| status | TEXT | ai / human / closed |
| ai_enabled | BOOLEAN | true by default, false after human replies or user escalates |
| created_at | DATETIME | |
| closed_at | DATETIME | nullable |
| closed_by | INTEGER | admin telegram_id |

### messages
| column | type | notes |
|---|---|---|
| id | INTEGER PK | |
| conversation_id | INTEGER FK | |
| role | TEXT | user / ai / agent |
| text | TEXT | |
| timestamp | DATETIME | |

## AI Client Interface

```python
async def send_message(history: list[dict], system_prompt: str) -> str:
    # history: [{"role": "user"/"assistant", "content": "..."}]
    # returns AI reply text
```

Provider is selected via `AI_PROVIDER` env var (`claude` or `openai`).
Model is set via `AI_MODEL` env var.

## Environment Variables

```
BOT_TOKEN=
AI_PROVIDER=claude          # claude | openai
AI_MODEL=claude-opus-4-6
AI_API_KEY=
AI_BASE_URL=                # optional, for openai-compatible APIs
AI_SYSTEM_PROMPT=You are a helpful support assistant.
DB_PATH=./data/bot.db
```

## i18n

Language is detected from `message.from_user.language_code` at first contact, stored in DB.
Fallback: English.

Keys live in `bot/locales/{lang}.json`. Translator injected via middleware as `message.translator`.

## Development with ao

Each module is a separate GitHub issue → separate ao agent session in a git worktree.

Modules:
1. DB layer (models + queries)
2. AI client
3. User handlers
4. Admin handlers
5. i18n middleware + locales
6. Docker + Makefile + config
