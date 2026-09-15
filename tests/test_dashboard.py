from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import get_session
from app.main import app

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
    response = client.get(
        "/api/v1/dashboard/report",
        headers={"Authorization": "Bearer changeme"},
    )

    assert response.status_code == 200

    body = response.json()
    assert body["project_name"] == "Luma Spend"
    assert body["period"]["label"] == "Últimos 12 meses"
    assert body["summary"][0]["name"] == "Gasto"
    assert len(body["spending_trend"]) == 12
    assert len(body["top_products"]) >= 4
    assert len(body["purchase_heatmap"]) >= 1
    assert len(body["price_reports"]) >= 1
    assert body["visit_summary"]["ticket_count"] >= 1
    assert len(body["product_quantities"]) >= 1
    assert len(body["recent_tickets"]) >= 1
    assert len(body["suggested_questions"]) >= 5


def test_dashboard_view_returns_html() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "Luma Spend" in response.text
    assert "api('/api/v1/dashboard/report'" in response.text
    assert "Pregunta a tus tickets" in response.text
    assert "Añadir ticket" in response.text
