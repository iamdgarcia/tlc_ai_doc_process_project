from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "Process Documents API")
    environment: str = os.getenv("ENVIRONMENT", "development")
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_base_url: str | None = os.getenv("BASE_URL")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    openai_chat_model: str = os.getenv("OPENAI_CHAT_MODEL", "zai-org/glm-5.3-flash")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./receipts.db")


settings = Settings()
