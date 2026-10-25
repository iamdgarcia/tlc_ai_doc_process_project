from __future__ import annotations

import hmac
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Form, HTTPException, Response, status
from fastapi.responses import HTMLResponse
from fastapi.security import OAuth2PasswordBearer

from app.api.v1.router import router as v1_router
from app.core.config import settings, validate_settings
from app.db.session import SessionLocal, engine
from app.models import Base
from app.services.job_recovery import fail_stale_jobs

_DASHBOARD_HTML = Path(__file__).resolve().parents[2] / "docs" / "dashboard_mock.html"

Base.metadata.create_all(bind=engine)

MASTER_KEY = settings.master_key

# Falla al importar (= al arrancar el contenedor) antes de servir nada.
validate_settings(environment=settings.environment, master_key=MASTER_KEY)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Al arrancar, cierra los jobs que murieron con el proceso anterior."""
    with SessionLocal() as session:
        recovered = fail_stale_jobs(session)
    if recovered:
        logger.warning("Marked %s interrupted job(s) as failed on startup", recovered)
    yield


app = FastAPI(title="Process Documents API", version="0.1.0", lifespan=lifespan)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def _secret_matches(candidate: str) -> bool:
    """Constant-time comparison; encoding acepta cualquier carácter sin TypeError."""
    return hmac.compare_digest(candidate.encode("utf-8"), MASTER_KEY.encode("utf-8"))


@app.post("/token")
async def login(password: Annotated[str, Form()]):
    if not _secret_matches(password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid master key")
    return {"access_token": password, "token_type": "bearer"}


async def verify_token(token: Annotated[str, Depends(oauth2_scheme)]):
    if not _secret_matches(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(status_code=204)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard_view() -> HTMLResponse:
    return HTMLResponse(_DASHBOARD_HTML.read_text(encoding="utf-8"))


# Health is public; everything else requires auth.
from app.api.v1.health import router as health_router  # noqa: E402

app.include_router(health_router)  # /health
app.include_router(health_router, prefix="/api/v1")  # /api/v1/health
app.include_router(v1_router, prefix="/api/v1", dependencies=[Depends(verify_token)])
