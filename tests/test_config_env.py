"""Config honesty: env var precedence and .env.example coverage."""

from __future__ import annotations

from pathlib import Path

from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[1]


def test_settings_prefers_openai_base_url(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.novita.ai/v3/openai")
    monkeypatch.delenv("BASE_URL", raising=False)

    assert Settings().openai_base_url == "https://api.novita.ai/v3/openai"


def test_settings_falls_back_to_legacy_base_url(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setenv("BASE_URL", "https://legacy.example/v1")

    assert Settings().openai_base_url == "https://legacy.example/v1"


def test_settings_openai_base_url_is_none_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("BASE_URL", raising=False)

    assert Settings().openai_base_url is None


def test_settings_reads_env_at_instantiation(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")

    assert Settings().environment == "production"


def test_env_example_covers_every_config_field() -> None:
    """El .env.example debe documentar todas las variables que lee config.py."""

    documented = (ROOT / ".env.example").read_text(encoding="utf-8")
    for env_name in (
        "APP_NAME",
        "ENVIRONMENT",
        "MASTER_KEY",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_MODEL",
        "OPENAI_CHAT_MODEL",
        "OCR_MODEL",
        "SCANEAME_API_KEY",
        "SCANEAME_API_URL",
        "SCANEAME_ENDPOINT",
        "SCANEAME_REQUEST_TIMEOUT_SECONDS",
        "SCANEAME_PROCESSING_TIMEOUT_SECONDS",
        "SCANEAME_POLL_INTERVAL_SECONDS",
        "DATABASE_URL",
    ):
        assert env_name in documented, f"{env_name} missing from .env.example"
