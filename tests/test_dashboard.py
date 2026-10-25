from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_dashboard_report_returns_mock_payload(api_client) -> None:
    with patch("app.main.MASTER_KEY", "test-master-key"):
        response = api_client.get(
            "/api/v1/dashboard/report",
            headers={"Authorization": "Bearer test-master-key"},
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
