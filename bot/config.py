from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    bot_token: str
    ai_provider: str = "claude"
    ai_model: str = "claude-opus-4-6"
    ai_api_key: str
    ai_base_url: str = ""
    ai_system_prompt: str = "You are a helpful support assistant."
    db_path: str = "./data/bot.db"

    class Config:
        env_file = ".env"


settings = Settings()
