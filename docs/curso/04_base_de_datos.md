# Módulo 04 — Base de Datos: SQLAlchemy + Alembic

**Ficheros:** `src/app/models/` · `src/app/repositories/` · `alembic/`

---

## Modelo de datos

![Modelo de datos](/docs/data_model.png)

Cuatro tablas con una relación en cadena:

```
supermercado (1) ──→ (N) ticket (1) ──→ (N) linea_ticket (N) ←── (1) producto
```

```python
# models/supermercado.py
class Supermercado(Base):
    id_supermercado: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100))
    codigo: Mapped[str | None] = mapped_column(String(20))

# models/ticket.py
class Ticket(Base):
    id_ticket: Mapped[str] = mapped_column(String(50), primary_key=True)  # PK natural
    id_supermercado: Mapped[int] = mapped_column(ForeignKey("supermercado.id_supermercado"))
    dia: Mapped[date]
    hora: Mapped[time | None]
    total: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))

# models/linea_ticket.py
class LineaTicket(Base):
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    id_ticket: Mapped[str] = mapped_column(ForeignKey("ticket.id_ticket", ondelete="CASCADE"))
    id_producto: Mapped[int] = mapped_column(ForeignKey("producto.id_producto"))
    cantidad_valor: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    cantidad_unidad: Mapped[str | None] = mapped_column(String(20))
    precio: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
```

**Por qué `id_ticket` es un `VARCHAR` y no `INTEGER`**: el número de ticket viene del documento físico. No es un ID generado por nosotros — es la referencia impresa en el papel. Usar la PK natural evita duplicados si el mismo ticket se sube dos veces.

---

## Patrón Repository

`SQLDocumentRepository` separa el acceso a datos de la lógica de negocio. Los servicios solo llaman a métodos del repositorio, nunca escriben SQL directamente:

```python
class SQLDocumentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, extraction: StructuredExtraction) -> None:
        supermercado = self._upsert_supermercado(extraction.supermercado.nombre_supermercado)
        ticket = self._upsert_ticket(extraction, supermercado.id_supermercado)
        self._replace_lineas(ticket.id_ticket, extraction.productos)

    def get_ticket_list(self, limit: int) -> list[dict]: ...
    def get_ticket_data(self, ticket_id: str) -> dict: ...
```

---

## Upsert patterns

### Supermercado: get-or-create por nombre

```python
def _upsert_supermercado(self, nombre: str) -> Supermercado:
    existing = self._session.scalar(
        select(Supermercado).where(Supermercado.nombre == nombre)
    )
    if existing:
        return existing
    new = Supermercado(nombre=nombre)
    self._session.add(new)
    self._session.flush()
    return new
```

### Ticket: INSERT OR REPLACE

Si el mismo ticket se sube dos veces (por error o para corregirlo), se sobreescribe completamente.

### Producto: fuzzy matching con rapidfuzz

El problema: el LLM puede extraer `"leche entera"` en un ticket y `"leche entera brick"` en otro. Son el mismo producto.

```python
from rapidfuzz import process, fuzz

def _upsert_producto(self, nombre: str) -> Producto:
    nombres_existentes = [p.nombre for p in self._session.scalars(select(Producto))]
    match = process.extractOne(nombre, nombres_existentes, scorer=fuzz.token_sort_ratio)

    if match and match[1] >= 85:  # umbral de similitud
        return self._session.scalar(select(Producto).where(Producto.nombre == match[0]))

    nuevo = Producto(nombre=nombre)
    self._session.add(nuevo)
    self._session.flush()
    return nuevo
```

### Líneas del ticket: borrar y reinsertar

Más simple que un diff: si el ticket ya existe, se borran todas sus líneas y se insertan las nuevas.

```python
def _replace_lineas(self, id_ticket: str, productos: list) -> None:
    self._session.execute(
        delete(LineaTicket).where(LineaTicket.id_ticket == id_ticket)
    )
    for producto in productos:
        linea = LineaTicket(id_ticket=id_ticket, ...)
        self._session.add(linea)
```

---

## Alembic: migraciones como código

```bash
# Crear una migración a partir de los cambios en los modelos
alembic revision --autogenerate -m "initial schema"

# Aplicar migraciones pendientes
alembic upgrade head

# Ver el estado actual
alembic current
```

Las migraciones son archivos Python en `alembic/versions/`. Se versionan en git junto al código.

---

## SQLite en dev, PostgreSQL en prod

La misma codebase funciona en ambos motores porque SQLAlchemy abstrae las diferencias:

```python
# .env local
DATABASE_URL=sqlite:///./receipts.db

# Railway (producción)
DATABASE_URL=postgresql://user:pass@host:5432/dbname
```

El único cambio al hacer la transición es la URL de conexión.

---

## Siguiente módulo

→ [05 — Agente Conversacional con Tool Calling](05_agente.md)
