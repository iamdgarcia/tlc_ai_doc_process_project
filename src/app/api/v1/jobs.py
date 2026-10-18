from __future__ import annotations

from collections import Counter
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.models.job import Job

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.get("/batch/{batch_id}", summary="Poll the status of an async extraction batch")
def get_batch_status(
    batch_id: str,
    session: Annotated[Session, Depends(get_session)],
    response: Response,
) -> dict:
    jobs = session.query(Job).filter_by(batch_id=batch_id).order_by(Job.created_at).all()
    if not jobs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found")

    counts = Counter(j.status for j in jobs)
    pending = counts.get("pending", 0)
    processing = counts.get("processing", 0)
    complete = pending + processing == 0

    if not complete:
        response.headers["Retry-After"] = "2"

    return {
        "batch_id": batch_id,
        "total": len(jobs),
        "pending": pending,
        "processing": processing,
        "done": counts.get("done", 0),
        "failed": counts.get("failed", 0),
        "complete": complete,
        "jobs": [
            {
                "job_id": j.id,
                "filename": j.filename,
                "status": j.status,
                "ticket_id": j.ticket_id,
                "error": j.error,
            }
            for j in jobs
        ],
    }
