from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.repositories.analytics import AnalyticsRepository
from app.repositories.dashboard import DashboardRepository
from app.services.chat import CHAT_TOOLS, ChatService

DB_PATH = Path(__file__).resolve().parents[1] / "receipt_mock.db"


@pytest.fixture
def session():
    with Session(create_engine(f"sqlite:///{DB_PATH}")) as database_session:
        yield database_session


def test_dashboard_exposes_chat_first_analytics(session) -> None:
    report = DashboardRepository(session).get_report()

    assert report.visit_summary.ticket_count == 5
    assert report.visit_summary.shopping_days == 4
    assert report.product_quantities
    assert report.recent_tickets[0].date == "2026-05-26"
    assert len(report.purchase_distribution.months) == 12
    assert len(report.purchase_distribution.weekdays) == 7
    assert len(report.purchase_distribution.hours) == 24
    assert sum(item.purchase_count for item in report.purchase_distribution.months) == 5
    assert {question.tool_name for question in report.suggested_questions} >= {
        "get_purchase_frequency",
        "get_product_quantities",
        "compare_product_prices",
    }


def test_analytics_compares_the_same_product_over_time(session) -> None:
    result = AnalyticsRepository(session).compare_product_prices("pechuga familiar")

    assert result["found"] is True
    assert result["product"] == "pechuga familiar"
    assert result["observations"] == 5
    assert result["first_price"] == pytest.approx(6.94)
    assert result["latest_price"] == pytest.approx(6.85)
    assert result["percentage_change"] == pytest.approx(-1.3)


def test_analytics_keeps_quantity_units_separate(session) -> None:
    result = AnalyticsRepository(session).get_product_quantities(days=365, limit=100)

    assert result["products"]
    bananas = [item for item in result["products"] if item["name"] == "banana"]
    assert bananas
    assert bananas[0]["unit"] == "kg"


def test_chat_exposes_frequent_analytics_as_tools(session) -> None:
    tool_names = {tool["function"]["name"] for tool in CHAT_TOOLS}
    service = ChatService(session=session, client=object())

    assert {
        "get_purchase_frequency",
        "get_spending_summary",
        "get_product_quantities",
        "compare_product_prices",
        "get_frequent_questions",
    } <= tool_names
    assert service._handle_tool_call(
        "get_purchase_frequency", {"days": 365}
    )["ticket_count"] == 5
