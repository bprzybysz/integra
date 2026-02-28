"""Configuration via environment variables."""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from .env file."""

    # Anthropic
    anthropic_api_key: str = ""

    # Telegram HIL
    telegram_bot_token: str = ""
    telegram_admin_chat_id: str = ""

    # Data Lake
    age_recipient: str = ""
    data_raw_path: Path = Path("data/raw")
    data_lake_path: Path = Path("data/lake")
    data_audit_path: Path = Path("data/audit")

    # Locale
    timezone: str = "Europe/Warsaw"
    locale: str = "pl-PL"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
