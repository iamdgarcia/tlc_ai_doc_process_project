from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Form, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.security import OAuth2PasswordBearer

from app.api.v1.router import router as v1_router
from app.db.session import engine
from app.models import Base

_DASHBOARD_HTML = Path(__file__).resolve().parents[2] / "docs" / "dashboard_mock.html"

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Process Documents API", version="0.1.0")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

MASTER_KEY = os.getenv("MASTER_KEY", "changeme")


@app.post("/token")
async def login(password: Annotated[str, Form()]):
    if password != MASTER_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid master key")
    return {"access_token": password, "token_type": "bearer"}


async def verify_token(token: Annotated[str, Depends(oauth2_scheme)]):
    if token != MASTER_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard_view() -> HTMLResponse:
    return HTMLResponse(_DASHBOARD_HTML.read_text(encoding="utf-8"))


app.include_router(v1_router, prefix="/api/v1", dependencies=[Depends(verify_token)])
