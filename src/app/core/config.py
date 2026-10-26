from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()

# Valores que saben públicos (README, repo): nunca válidos como clave maestra en producción.
INSECURE_MASTER_KEYS = frozenset({"changeme", "change-me", "change-me-in-dev"})


def validate_settings(environment: str, master_key: str | None) -> None:
    """Fail fast on insecure configuration before the app starts serving.

    En producción no puede arrancar la API con la clave por defecto del README:
    mejor un contenedor caído que la API abierta con una clave pública.
    """
    # Normaliza casing: ENVIRONMENT=Production debe pasar por el mismo guard
    # que "production" (un comparador exacto lo saltaba entero).
    if (environment or "").strip().lower() != "production":
        return
    key = (master_key or "").strip()
    if not key or key.lower() in INSECURE_MASTER_KEYS:
        raise RuntimeError(
            "MASTER_KEY must be set to a strong secret when ENVIRONMENT=production "
            "(unset, empty or a known default like 'changeme' refuses to boot)."
        )


def _env(key: str, default: str | None = None) -> str | None:
    return os.getenv(key, default)


@dataclass(frozen=True)
class Settings:
    """Configuración leída del entorno en cada instanciación (testeable con monkeypatch)."""

    app_name: str = field(default_factory=lambda: _env("APP_NAME", "Process Documents API"))
    environment: str = field(default_factory=lambda: _env("ENVIRONMENT", "development"))
    master_key: str = field(default_factory=lambda: _env("MASTER_KEY", "changeme"))
    scaneame_api_key: str | None = field(default_factory=lambda: _env("SCANEAME_API_KEY"))
    scaneame_api_url: str = field(
        default_factory=lambda: _env(
            "SCANEAME_API_URL", "https://scaneame.iamdgarcia.com/v1/process"
        )
    )
    scaneame_endpoint: str = field(default_factory=lambda: _env("SCANEAME_ENDPOINT", "tickets"))
    scaneame_request_timeout_seconds: float = field(
        default_factory=lambda: float(_env("SCANEAME_REQUEST_TIMEOUT_SECONDS", "60"))
    )
    scaneame_processing_timeout_seconds: float = field(
        default_factory=lambda: float(_env("SCANEAME_PROCESSING_TIMEOUT_SECONDS", "90"))
    )
    scaneame_poll_interval_seconds: float = field(
        default_factory=lambda: float(_env("SCANEAME_POLL_INTERVAL_SECONDS", "1"))
    )
    openai_api_key: str | None = field(default_factory=lambda: _env("OPENAI_API_KEY"))
    # El nombre documentado gana; BASE_URL se mantiene por compatibilidad con
    # los despliegues existentes.
    openai_base_url: str | None = field(
        default_factory=lambda: _env("OPENAI_BASE_URL") or _env("BASE_URL")
    )
    openai_model: str = field(default_factory=lambda: _env("OPENAI_MODEL", "gpt-4.1-mini"))
    openai_chat_model: str = field(
        default_factory=lambda: _env("OPENAI_CHAT_MODEL", "google/gemma-4-31b-it")
    )
    ocr_model: str = field(
        default_factory=lambda: _env("OCR_MODEL", "deepseek/deepseek-ocr-2")
    )
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL", "sqlite:///./receipts.db"))


settings = Settings()
