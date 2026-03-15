from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    bot_token: str
    ai_provider: str = "claude"
    ai_model: str = "claude-opus-4-6"
    ai_api_key: str = ""
    ai_base_url: str = ""
    ai_system_prompt: str = "You are a helpful support assistant."
    db_path: str = "./data/bot.db"
    admin_ids: List[int] = []
    log_level: str = "INFO"


settings = Settings()
