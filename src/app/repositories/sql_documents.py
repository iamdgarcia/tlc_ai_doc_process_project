from __future__ import annotations

import datetime

from sqlalchemy.orm import Session

from app.models.linea_ticket import LineaTicket
from app.models.producto import Producto
from app.models.supermercado import Supermercado
from app.models.ticket import Ticket
from app.schemas.extraction import StructuredExtraction
from app.utils.cantidad_parser import parse_cantidad


class SQLDocumentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, extraction: StructuredExtraction) -> int:
        """Upsert a ticket and its lines. Returns the number of lines saved."""
        if not extraction.id_ticket:
            raise ValueError("id_ticket is required but was None or empty")

        try:
            supermercado = self._get_or_create_supermercado(
                extraction.supermercado.nombre_supermercado or ""
            )

            ticket = self._session.get(Ticket, extraction.id_ticket)
            #Comprueba si el ticket existe, si no, crea uno nuevo
            if ticket is None:
                print(f"Creating new ticket with id_ticket: {extraction.id_ticket}")
                ticket = Ticket(id_ticket=extraction.id_ticket)
                self._session.add(ticket)
            else:
                print(f"Updating existing ticket with id_ticket: {extraction.id_ticket}")
            ticket.id_supermercado = supermercado.id_supermercado
            ticket.dia = datetime.date.fromisoformat(extraction.dia or "")
            ticket.hora = datetime.time.fromisoformat(extraction.hora or "")
            ticket.total = extraction.total or 0

            self._session.query(LineaTicket).filter_by(id_ticket=ticket.id_ticket).delete()

            for producto_data in extraction.productos:
                nombre = (producto_data.nombre_producto or "").strip().lower()
                if not nombre:
                    continue
                nombre_raw = nombre
                nombre = self.similar_fuzzy_product(nombre) or nombre
                if nombre != nombre_raw:
                    print(f"Fuzzy matched '{nombre_raw}' to '{nombre}'")
                producto = self._get_or_create_producto(nombre)
                cantidad_valor, cantidad_unidad = parse_cantidad(
                    str(producto_data.cantidad) if producto_data.cantidad is not None else None
                )
                linea = LineaTicket(
                    id_ticket=ticket.id_ticket,
                    id_producto=producto.id_producto,
                    cantidad_valor=cantidad_valor,
                    cantidad_unidad=cantidad_unidad,
                    precio=producto_data.precio,
                )
                self._session.add(linea)

            self._session.commit()
        except Exception:
            self._session.rollback()
            raise

        return len(extraction.productos)

    def _get_or_create_supermercado(self, nombre: str) -> Supermercado:
        nombre = nombre.strip().lower()
        sm = self._session.query(Supermercado).filter_by(nombre=nombre).first()
        if sm is None:
            print(f"Creating new supermercado with nombre: {nombre}")
            sm = Supermercado(nombre=nombre)
            self._session.add(sm)
            self._session.flush()
        else:
            print(f"Found existing supermercado with nombre: {nombre}")
        return sm

    def _get_or_create_producto(self, nombre: str) -> Producto:
        p = self._session.query(Producto).filter_by(nombre=nombre).first()
        if p is None:
            print(f"Creating new producto with nombre: {nombre}")
            p = Producto(nombre=nombre)
            self._session.add(p)
            self._session.flush()
        else:
            print(f"Found existing producto with nombre: {nombre}")
        return p

    def get_supermercado_list(self) -> list[str]:
        """Return a list of all known supermarket names."""
        return [sm.nombre for sm in self._session.query(Supermercado).all()]


    def get_producto_list(self) -> list[str]:
        """Return a list of all known product names."""
        return [p.nombre for p in self._session.query(Producto).all()]

    def similar_fuzzy_product(self, product_name: str, threshold: int = 80) -> str | None:
        """Return the most similar product from the database using fuzzy matching, none otherwise."""
        from rapidfuzz import fuzz, process

        # Normalize input
        product_name = product_name.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
        product_name = product_name.lower()

        products_bbdd = self.get_producto_list()
        results = process.extract(product_name, products_bbdd, scorer=fuzz.ratio, limit=3)
        for match in results:
            if match[1] >= threshold:
                return match[0]
        return None