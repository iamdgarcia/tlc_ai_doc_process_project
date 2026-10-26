from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import validate_settings
from app.main import app


client = TestClient(app)


def test_protected_route_rejects_missing_token() -> None:
    response = client.get("/api/v1/dashboard/report")

    assert response.status_code == 401


def test_protected_route_rejects_wrong_token() -> None:
    response = client.get(
        "/api/v1/dashboard/report",
        headers={"Authorization": "Bearer not-the-master-key"},
    )

    assert response.status_code == 401


def test_token_login_rejects_wrong_password() -> None:
    with patch("app.main.MASTER_KEY", "test-master-key"):
        response = client.post("/token", data={"password": "not-it"})

    assert response.status_code == 401


def test_token_login_accepts_configured_password() -> None:
    with patch("app.main.MASTER_KEY", "test-master-key"):
        response = client.post("/token", data={"password": "test-master-key"})

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"


@pytest.mark.parametrize("master_key", [None, "", "   ", "changeme", "change-me"])
def test_validate_settings_fails_fast_in_production(master_key) -> None:
    with pytest.raises(RuntimeError, match="MASTER_KEY"):
        validate_settings(environment="production", master_key=master_key)


def test_validate_settings_allows_strong_key_in_production() -> None:
    validate_settings(environment="production", master_key="a-long-random-secret")


def test_validate_settings_normalizes_environment_casing() -> None:
    """ENVIRONMENT=Production no puede saltarse el guard por comparación exacta."""
    with pytest.raises(RuntimeError, match="MASTER_KEY"):
        validate_settings(environment="Production", master_key="changeme")
    with pytest.raises(RuntimeError, match="MASTER_KEY"):
        validate_settings(environment=" PRODUCTION ", master_key=None)


def test_validate_settings_keeps_dev_default_working() -> None:
    validate_settings(environment="development", master_key="changeme")
