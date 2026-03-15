from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    BOT_TOKEN: str
    AI_PROVIDER: str = "claude"
    AI_MODEL: str = "claude-opus-4-6"
    AI_API_KEY: str = ""
    AI_BASE_URL: str = ""
    AI_SYSTEM_PROMPT: str = "You are a helpful support assistant."
    DB_PATH: str = "./data/bot.db"
    # Comma-separated or JSON list of admin Telegram user IDs for capacity alerts
    ADMIN_IDS: List[int] = []
    LOG_LEVEL: str = "INFO"

    model_config = {"env_file": ".env"}


settings = Settings()
