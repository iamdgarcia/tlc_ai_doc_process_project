"""Stuck-job reconciliation: jobs orphaned by a restart must not wedge the UI."""

from __future__ import annotations

import datetime
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.main import app
from app.models import Base, Job
from app.services.job_recovery import fail_stale_jobs


def _engine_with_jobs():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


def test_fail_stale_jobs_marks_old_pending_and_processing_jobs_failed() -> None:
    engine = _engine_with_jobs()
    now = datetime.datetime(2026, 10, 25, 12, 0, 0)
    with Session(engine) as session:
        session.add_all(
            [
                Job(
                    id="j-old-pending",
                    batch_id="b1",
                    filename="a.jpg",
                    status="pending",
                    created_at=now - datetime.timedelta(seconds=301),
                ),
                Job(
                    id="j-old-processing",
                    batch_id="b1",
                    filename="b.jpg",
                    status="processing",
                    created_at=now - datetime.timedelta(hours=1),
                ),
                Job(
                    id="j-fresh",
                    batch_id="b1",
                    filename="c.jpg",
                    status="pending",
                    created_at=now - datetime.timedelta(seconds=1),
                ),
                Job(
                    id="j-done",
                    batch_id="b1",
                    filename="d.jpg",
                    status="done",
                    created_at=now - datetime.timedelta(days=1),
                ),
                Job(
                    id="j-failed",
                    batch_id="b1",
                    filename="e.jpg",
                    status="failed",
                    created_at=now - datetime.timedelta(days=1),
                ),
            ]
        )
        session.commit()

        recovered = fail_stale_jobs(session, stale_after_seconds=300, now=now)

        assert recovered == 2
        old_pending = session.get(Job, "j-old-pending")
        assert old_pending.status == "failed"
        assert "Interrumpido" in (old_pending.error or "")
        assert session.get(Job, "j-old-processing").status == "failed"
        assert session.get(Job, "j-fresh").status == "pending"
        assert session.get(Job, "j-done").status == "done"
        assert session.get(Job, "j-failed").status == "failed"


def test_startup_lifespan_runs_the_job_sweep_once() -> None:
    calls: list[object] = []

    def fake_fail_stale_jobs(session, **_: object) -> int:
        calls.append(session)
        return 0

    with patch("app.main.fail_stale_jobs", fake_fail_stale_jobs):
        with TestClient(app) as client:
            assert client.get("/health").status_code == 200

    assert len(calls) == 1
