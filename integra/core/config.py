"""Configuration via environment variables."""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from .env file."""

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-4-6"

    # Telegram HIL
    telegram_bot_token: str = ""
    telegram_admin_chat_id: int = 0

    # Data Lake
    age_recipient: str = ""
    age_identity: str = ""
    data_raw_path: Path = Path("data/raw")
    data_lake_path: Path = Path("data/lake")
    data_audit_path: Path = Path("data/audit")

    # Scheduler
    schedule_morning: str = "08:00"
    schedule_evening: str = "21:00"
    schedule_enabled: bool = True

    # Locale
    timezone: str = "Europe/Warsaw"
    locale: str = "pl-PL"

    # App
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
