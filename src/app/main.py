from __future__ import annotations

from fastapi import FastAPI

from app.api.v1.health import health_check
from app.api.v1.router import router as v1_router
from app.db.session import engine
from app.models import Base

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Process Documents API", version="0.1.0")
#TODO: Create basic authentication for the API endpoints

app.get("/health", tags=["health"])(health_check)
app.include_router(v1_router, prefix="/api/v1")
