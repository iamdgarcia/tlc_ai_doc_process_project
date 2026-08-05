from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db.session import get_session


DB_PATH = Path(__file__).resolve().parents[1] / "receipt_mock.db"
engine = create_engine(f"sqlite:///{DB_PATH}")
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


client = TestClient(app)


def override_get_session():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


app.dependency_overrides[get_session] = override_get_session


def test_dashboard_report_returns_mock_payload() -> None:
    response = client.get("/api/v1/dashboard/report")

    assert response.status_code == 200

    body = response.json()
    assert body["project_name"] == "Luma Spend"
    assert body["period"]["label"] == "Últimos 12 meses"
    assert body["summary"][0]["name"] == "Gasto"
    assert len(body["spending_trend"]) == 12
    assert len(body["top_products"]) >= 4
    assert len(body["purchase_heatmap"]) >= 1
    assert len(body["price_reports"]) >= 1


def test_dashboard_view_returns_html() -> None:
    response = client.get("/api/v1/dashboard")

    assert response.status_code == 200
    assert "Luma Spend" in response.text
    assert "fetch('/api/v1/dashboard/report')" in response.text
