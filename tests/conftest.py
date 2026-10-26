"""Shared fixtures: in-memory engine with a deterministic dataset."""

import datetime
import os
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# app.main ejecuta Base.metadata.create_all al importar sobre el engine de
# DATABASE_URL (default sqlite:///./receipts.db): sin esto, cada corrida de
# pytest escribe/crea receipts.db en la raíz del repo. Fichero temporal del
# propio harness, fijado ANTES del primer import de app.main (conftest importa
# antes que cualquier módulo de tests, así que ahí es donde aplica).
os.environ["DATABASE_URL"] = "sqlite:///" + str(
    (Path(tempfile.mkdtemp(prefix="docproc-tests-")) / "receipts.db").as_posix()
)

from app.db.session import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, LineaTicket, Producto, Supermercado, Ticket  # noqa: E402


def make_seeded_engine():
    """In-memory SQLite with the full app schema and a deterministic dataset.

    StaticPool keeps one shared connection so the session is visible across
    the threads TestClient uses to run the app.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    _seed(engine)
    return engine


def _seed(engine) -> None:
    """Seed a small dataset: 5 tickets / 5 products / 2 stores, newest 2026-10-01.

    Everything downstream (analytics periods, dashboard windows) anchors on the
    max ticket date, so fixed dates keep every assertion deterministic forever.
    """
    mercadona = Supermercado(nombre="mercadona")
    carrefour = Supermercado(nombre="carrefour")
    pechuga = Producto(nombre="pechuga familiar")
    banana = Producto(nombre="banana")
    leche = Producto(nombre="leche entera")
    pan = Producto(nombre="pan de molde")
    tomate = Producto(nombre="tomate")

    tickets = [
        (
            Ticket(
                id_ticket="T-SEED-001",
                supermercado=mercadona,
                dia=datetime.date(2026, 5, 10),
                hora=datetime.time(12, 30),
                total=Decimal("10.50"),
            ),
            [
                (pechuga, "1", "ud", "5.50"),
                (banana, "1", "kg", "1.50"),
                (pan, "1", "ud", "1.10"),
                (leche, "2", "l", "2.40"),
            ],
        ),
        (
            Ticket(
                id_ticket="T-SEED-002",
                supermercado=mercadona,
                dia=datetime.date(2026, 6, 15),
                hora=datetime.time(18, 45),
                total=Decimal("8.75"),
            ),
            [
                (pechuga, "1", "ud", "5.75"),
                (banana, "2", "kg", "3.00"),
            ],
        ),
        (
            Ticket(
                id_ticket="T-SEED-003",
                supermercado=carrefour,
                dia=datetime.date(2026, 8, 1),
                hora=datetime.time(10, 15),
                total=Decimal("3.50"),
            ),
            [
                (tomate, "1", "kg", "2.30"),
                (leche, "1", "l", "1.20"),
            ],
        ),
        (
            Ticket(
                id_ticket="T-SEED-004",
                supermercado=mercadona,
                dia=datetime.date(2026, 9, 20),
                hora=datetime.time(19, 5),
                total=Decimal("7.75"),
            ),
            [
                (pechuga, "1", "ud", "6.10"),
                (banana, "1", "kg", "1.65"),
            ],
        ),
        (
            Ticket(
                id_ticket="T-SEED-005",
                supermercado=mercadona,
                dia=datetime.date(2026, 10, 1),
                hora=datetime.time(13, 0),
                total=Decimal("5.40"),
            ),
            [
                (leche, "6", "ud", "5.40"),
            ],
        ),
    ]

    with Session(engine) as session:
        session.add_all([mercadona, carrefour])
        session.add_all([pechuga, banana, leche, pan, tomate])
        session.flush()  # asigna los ids autogenerados antes de crear las líneas
        for ticket, lines in tickets:
            session.add(ticket)
            for product, quantity, unit, price in lines:
                session.add(
                    LineaTicket(
                        id_ticket=ticket.id_ticket,
                        id_producto=product.id_producto,
                        cantidad_valor=Decimal(quantity),
                        cantidad_unidad=unit,
                        precio=Decimal(price),
                    )
                )
        session.commit()


@pytest.fixture
def seeded_engine():
    engine = make_seeded_engine()
    yield engine
    engine.dispose()


@pytest.fixture
def session(seeded_engine):
    with Session(seeded_engine) as database_session:
        yield database_session


@pytest.fixture
def api_client(seeded_engine):
    """TestClient with the app DB dependency pointed at the seeded in-memory DB.

    Does not enter the app lifespan, so no startup side effects run.
    """
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=seeded_engine)

    def override_get_session():
        database_session = TestingSessionLocal()
        try:
            yield database_session
        finally:
            database_session.close()

    app.dependency_overrides[get_session] = override_get_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)
