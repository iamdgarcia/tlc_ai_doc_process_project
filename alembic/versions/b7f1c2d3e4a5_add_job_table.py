"""add job table

Revision ID: b7f1c2d3e4a5
Revises: 5c840a1a73a6
Create Date: 2026-10-25

La tabla `job` (src/app/models/job.py) faltaba en el esquema inicial: cualquier
base creada solo con `alembic upgrade head` no tenía `job` y los endpoints
de extracción asíncrona fallaban con "no such table: job".
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7f1c2d3e4a5"
down_revision: Union[str, Sequence[str], None] = "5c840a1a73a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the job table backing /api/v1/jobs, mirroring src/app/models/job.py."""
    op.create_table(
        "job",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("ticket_id", sa.String(length=50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_job_batch_id"), "job", ["batch_id"], unique=False)


def downgrade() -> None:
    """Remove the job table."""
    op.drop_index(op.f("ix_job_batch_id"), table_name="job")
    op.drop_table("job")
