from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas.dashboard import (
    DashboardReport,
)
from app.repositories.dashboard import DashboardRepository

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

ROOT_DIR = Path(__file__).resolve().parents[4]
DASHBOARD_HTML_PATH = ROOT_DIR / "docs" / "dashboard_mock.html"


@router.get(
    "",
    response_class=HTMLResponse,
    summary="Render dashboard mock HTML",
)
async def dashboard_view() -> HTMLResponse:
    """Render the dashboard mock page that consumes the report endpoint."""

    return HTMLResponse(DASHBOARD_HTML_PATH.read_text(encoding="utf-8"))


@router.get(
    "/report",
    response_model=DashboardReport,
    summary="Get dashboard monitoring report",
)
async def get_dashboard_report(session: Session = Depends(get_session)) -> DashboardReport:
    """Return the dashboard report built from the database."""

    repository = DashboardRepository(session)
    return repository.get_report()


