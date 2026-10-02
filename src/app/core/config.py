from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "Process Documents API")
    environment: str = os.getenv("ENVIRONMENT", "development")
    scaneame_api_key: str | None = os.getenv("SCANEAME_API_KEY")
    scaneame_api_url: str = os.getenv(
        "SCANEAME_API_URL", "https://scaneame.iamdgarcia.com/v1/process"
    )
    scaneame_endpoint: str = os.getenv("SCANEAME_ENDPOINT", "tickets")
    scaneame_request_timeout_seconds: float = float(
        os.getenv("SCANEAME_REQUEST_TIMEOUT_SECONDS", "60")
    )
    scaneame_processing_timeout_seconds: float = float(
        os.getenv("SCANEAME_PROCESSING_TIMEOUT_SECONDS", "180")
    )
    scaneame_poll_interval_seconds: float = float(
        os.getenv("SCANEAME_POLL_INTERVAL_SECONDS", "1")
    )
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_base_url: str | None = os.getenv("BASE_URL")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    openai_chat_model: str = os.getenv("OPENAI_CHAT_MODEL", "google/gemma-4-31b-it")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./receipts.db")


settings = Settings()
