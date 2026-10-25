from __future__ import annotations

import datetime
from datetime import timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.job import Job

# Los BackgroundTasks viven en el proceso y solo hay un worker uvicorn: en el
# instante del arranque no puede haber ningún job legítimo en vuelo. Todo
# pending/processing que llegue al boot es huérfano de un reinicio anterior, así
# que el umbral es 0 (un umbral positivo dejaba pendientes para siempre a los
# jobs encolados <5min antes de reiniciar).
STALE_JOB_SECONDS = 0


def fail_stale_jobs(
    session: Session,
    *,
    stale_after_seconds: float = STALE_JOB_SECONDS,
    now: datetime.datetime | None = None,
) -> int:
    """Mark every pending/processing job as failed (umbral 0 en el arranque).

    Sin esto, un job interrumpido por un reinicio se queda en pending/processing
    para siempre y el dashboard lo sondea indefinidamente. Devuelve cuántos marcó.
    """
    # created_at es naive (CURRENT_TIMESTAMP en UTC en SQLite; reloj del server
    # en Postgres): comparamos contra naive UTC como aproximación honesta.
    now = now or datetime.datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now - datetime.timedelta(seconds=stale_after_seconds)
    stale = list(
        session.scalars(
            select(Job).where(
                Job.status.in_(("pending", "processing")),
                Job.created_at < cutoff,
            )
        )
    )
    for job in stale:
        job.status = "failed"
        job.error = "Interrumpido por reinicio del servidor"
    if stale:
        session.commit()
    return len(stale)
