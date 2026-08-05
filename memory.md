# Memory - Process Documents API

## Sesión 2026-07-15

### Resumen rápido
- Inicialicé una estructura base para una API con `FastAPI` usando layout `src/`.
- Añadí endpoint `POST /api/v1/documents/extract` que recibe archivos (imagen o PDF).
- Implementé tests `pytest` y un `TestClient` para el endpoint de extracción y health.
- Integré un helper LLM (`llm_as_structured_output`) que prepara contexto (extrae texto de PDFs o codifica imágenes) y llama a la API OpenAI.
- Definí modelos Pydantic para la salida estructurada y ajusté el contrato según requisitos: devolvemos `supermercado`, `dia`, `hora`, `total` y `productos` (cada producto con `nombre_producto`, `cantidad` y `precio`).
- Implementé persistencia temporal en memoria (`InMemoryDocumentRepository`) para guardar resultados.
- Añadí `python-dotenv` y `load_dotenv()` para cargar `.env` automáticamente.

### Archivos clave creados/modificados
- `src/app/main.py` - app FastAPI
- `src/app/api/v1/extraction.py` - router `POST /api/v1/documents/extract`
- `src/app/api/v1/router.py` - registro de routers
- `src/app/services/llm.py` - helper LLM `llm_as_structured_output` y utilidades de extracción de PDFs/imagenes
- `src/app/services/document_extraction.py` - orquestador que llama al LLM y almacena resultado
- `src/app/repositories/documents.py` - repositorio en memoria (temporal)
- `src/app/schemas/extraction.py` - modelos Pydantic del contrato de salida
- `tests/test_extraction.py` y `tests/test_health.py` - pruebas unitarias
- `requirements.txt` y `README.md` - dependencias y notas de uso

### Entorno / variables
- `OPENAI_API_KEY` (obligatorio para llamada real al LLM)
- `OPENAI_MODEL` (opcional, por defecto `gpt-4.1-mini`)

---

## Sesión 2026-07-22

### Resumen rápido
- Corregido el prompt LLM para extraer correctamente `precio`, `cantidad` (separada del nombre) e `id_ticket`.
- Diseñada e implementada la arquitectura SQL completa con SQLAlchemy + Alembic + SQLite.
- Reemplazado `InMemoryDocumentRepository` por `SQLDocumentRepository` con upsert transaccional.
- 18 tests pasan (8 parser, 8 repositorio SQL, 1 extracción, 1 health).

### Decisiones de arquitectura
- **Catálogo normalizado**: tablas `supermercado`, `ticket`, `producto`, `linea_ticket` — productos reutilizados entre tickets via catálogo único.
- **id_ticket como PK**: extraído por el LLM del documento (VARCHAR 50). Si el LLM no lo encuentra devuelve 422.
- **Upsert por id_ticket**: si llega el mismo ticket, se actualiza (no se rechaza ni se duplica). Las líneas se borran y reinsertan completas.
- **cantidad en dos columnas**: `cantidad_valor NUMERIC` + `cantidad_unidad VARCHAR` — permite agregar por unidad en informes futuros.
- **SQLite local, PostgreSQL-ready**: solo cambia `DATABASE_URL`, el ORM no cambia.

### Archivos creados
- `src/app/models/base.py` — `DeclarativeBase`
- `src/app/models/supermercado.py` — ORM `Supermercado`
- `src/app/models/ticket.py` — ORM `Ticket`
- `src/app/models/producto.py` — ORM `Producto`
- `src/app/models/linea_ticket.py` — ORM `LineaTicket`
- `src/app/models/__init__.py` — re-exports para Alembic autodiscovery
- `src/app/db/session.py` — engine + `SessionLocal` + `get_session()`
- `src/app/repositories/sql_documents.py` — `SQLDocumentRepository` con upsert
- `src/app/utils/cantidad_parser.py` — `parse_cantidad("2kg") -> (2.0, "kg")`
- `alembic/` + `alembic.ini` — migraciones (migración inicial: 4 tablas)
- `tests/test_cantidad_parser.py` — 8 tests parametrizados
- `tests/test_sql_repository.py` — 8 tests de integración con SQLite in-memory

### Archivos modificados
- `src/app/schemas/extraction.py` — añadido `id_ticket: str | None`; `stored_document_id` cambiado de `int` a `str`
- `src/app/services/llm.py` — prompt actualizado: extrae `id_ticket`, `precio`, separa `nombre_producto` de `cantidad`
- `src/app/services/document_extraction.py` — usa `SQLDocumentRepository` vía DI; rechaza con 422 si `id_ticket` es None
- `src/app/api/v1/extraction.py` — inyecta `Session` vía `Depends(get_session)`
- `src/app/api/v1/dashboard.py` — eliminado import muerto de `extraction_service`
- `src/app/core/config.py` — añadido `database_url`
- `requirements.txt` — añadido `sqlalchemy>=2.0.0`, `alembic>=1.13.0`
- `.env` — añadido `DATABASE_URL=sqlite:///./receipts.db`
- `tests/test_extraction.py` — actualizado mock con `id_ticket` y `stored_document_id` como string

### Entorno / variables
- `DATABASE_URL` — por defecto `sqlite:///./receipts.db`

### Cómo ejecutar localmente
1. Activar `venv`:
```bash
source venv/bin/activate
```
2. Instalar dependencias:
```bash
pip install -r requirements.txt
```
3. Aplicar migraciones:
```bash
alembic upgrade head
```
4. Correr pruebas:
```bash
pytest tests/
```
5. Levantar server:
```bash
uvicorn app.main:app --reload --app-dir src
```

### Estado actual
- Tests: 18/18 pasan
- Persistencia: SQLite con Alembic (4 tablas normalizadas)
- Deduplicación: upsert por `id_ticket` (actualiza si existe)
- LLM: extrae `id_ticket`, `precio`, `cantidad` separada del nombre

---

## Sesión 2026-07-29

### Resumen rápido
- Rediseñado el dashboard HTML mock con un estilo claro tipo Stripe y nombre de proyecto `Luma Spend`.
- Definido el contrato del dashboard en `GET /api/v1/dashboard/report` con schema tipado en `src/app/schemas/dashboard.py`.
- Conectada la vista HTML en `GET /api/v1/dashboard` para hidratarse desde el endpoint `report` con `fetch`.
- Implementado `DashboardRepository` con queries reales sobre `ticket`, `linea_ticket`, `producto` y `supermercado`.
- Generado `receipt_mock.db` con datos de prueba y luego ampliado con más de 500 tickets del último año.
- Añadido test de integración para el endpoint y la vista HTML.

### Archivos clave creados/modificados
- `docs/dashboard_mock.html` - mock HTML conectado al endpoint
- `src/app/api/v1/dashboard.py` - vista HTML y endpoint `GET /report`
- `src/app/repositories/dashboard.py` - queries y agregaciones del dashboard
- `src/app/schemas/dashboard.py` - contrato del reporte de dashboard
- `tests/test_dashboard.py` - tests del endpoint y de la vista HTML
- `receipt_mock.db` - base SQLite de prueba con tickets de un año

### Estado actual
- El dashboard ya consume datos reales de la base mock.
- La DB de prueba contiene más de 500 tickets en el último año.
- La vista HTML y el endpoint JSON están conectados y validados con datos reales.

### Próximos pasos recomendados
- Implementar endpoints de reporting/agregación en `dashboard.py` (gasto por supermercado, por producto, por periodo)
- Añadir categorías a productos cuando haya fuente de datos
- Migrar a PostgreSQL cuando sea necesario (solo cambiar `DATABASE_URL`)
- Implementar chatbot en `dashboard.py /chat`
