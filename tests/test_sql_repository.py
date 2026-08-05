from __future__ import annotations

import datetime
import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Ticket, Producto, Supermercado, LineaTicket
from app.repositories.sql_documents import SQLDocumentRepository
from app.schemas.extraction import (
    ProductoCantidadExtraction,
    StructuredExtraction,
    SupermercadoExtraction,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


@pytest.fixture
def repo(session):
    return SQLDocumentRepository(session)


def _make_extraction(id_ticket: str = "T001") -> StructuredExtraction:
    return StructuredExtraction(
        id_ticket=id_ticket,
        supermercado=SupermercadoExtraction(nombre_supermercado="mercadona"),
        dia="2026-02-20",
        hora="17:06",
        total=88.07,
        productos=[
            ProductoCantidadExtraction(nombre_producto="mandarina", cantidad="2kg", precio=3.9),
            ProductoCantidadExtraction(nombre_producto="noquis de patata", cantidad="2", precio=2.0),
        ],
    )


def test_save_creates_ticket(repo, session):
    repo.save(_make_extraction())
    ticket = session.get(Ticket, "T001")
    assert ticket is not None
    assert ticket.dia == datetime.date(2026, 2, 20)
    assert float(ticket.total) == pytest.approx(88.07)


def test_save_creates_supermercado(repo, session):
    repo.save(_make_extraction())
    sm = session.query(Supermercado).filter_by(nombre="mercadona").first()
    assert sm is not None


def test_save_creates_productos(repo, session):
    repo.save(_make_extraction())
    nombres = [p.nombre for p in session.query(Producto).all()]
    assert "mandarina" in nombres
    assert "noquis de patata" in nombres


def test_save_creates_lineas_with_parsed_cantidad(repo, session):
    repo.save(_make_extraction())
    lineas = session.query(LineaTicket).all()
    assert len(lineas) == 2
    mandarina = next(l for l in lineas if l.producto.nombre == "mandarina")
    assert float(mandarina.cantidad_valor) == pytest.approx(2.0)
    assert mandarina.cantidad_unidad == "kg"


def test_save_deduplicates_supermercado(repo, session):
    repo.save(_make_extraction("T001"))
    repo.save(_make_extraction("T002"))
    count = session.query(Supermercado).count()
    assert count == 1


def test_save_deduplicates_producto(repo, session):
    repo.save(_make_extraction("T001"))
    repo.save(_make_extraction("T002"))
    count = session.query(Producto).filter_by(nombre="mandarina").count()
    assert count == 1


def test_upsert_updates_existing_ticket(repo, session):
    repo.save(_make_extraction())
    updated = StructuredExtraction(
        id_ticket="T001",
        supermercado=SupermercadoExtraction(nombre_supermercado="mercadona"),
        dia="2026-02-21",
        hora="10:00",
        total=99.0,
        productos=[
            ProductoCantidadExtraction(nombre_producto="mandarina", cantidad="1kg", precio=2.0),
        ],
    )
    repo.save(updated)
    ticket = session.get(Ticket, "T001")
    assert ticket.dia == datetime.date(2026, 2, 21)
    assert float(ticket.total) == pytest.approx(99.0)
    lineas = session.query(LineaTicket).filter_by(id_ticket="T001").all()
    assert len(lineas) == 1


def test_save_raises_if_id_ticket_is_none(repo):
    extraction = _make_extraction()
    extraction = extraction.model_copy(update={"id_ticket": None})
    with pytest.raises(ValueError, match="id_ticket"):
        repo.save(extraction)
