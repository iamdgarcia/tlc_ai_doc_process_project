from __future__ import annotations

import os
from typing import Annotated

from fastapi import Depends, FastAPI, Form, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.api.v1.router import router as v1_router
from app.db.session import engine
from app.models import Base

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


app.include_router(v1_router, prefix="/api/v1", dependencies=[Depends(verify_token)])
