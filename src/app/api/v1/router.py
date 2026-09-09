from fastapi import APIRouter

from app.api.v1.health import router as health_router
from app.api.v1.extraction import router as extraction_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.chat import router as chat_router
router = APIRouter()
router.include_router(health_router, tags=["health"])
router.include_router(extraction_router)
router.include_router(dashboard_router)
router.include_router(chat_router)
