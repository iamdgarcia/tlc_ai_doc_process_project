# Luma Spend — Curso Completo
> Construye una API de análisis de tickets de supermercado con FastAPI, LLMs y Railway

---

## Descripción del Proyecto

**Luma Spend** es una API REST que permite:
1. **Subir un ticket de supermercado** (imagen o PDF) y extraer sus datos de forma estructurada usando un LLM
2. **Almacenar los datos** en una base de datos relacional (SQLite en dev, PostgreSQL en prod)
3. **Consultar el historial de compras** mediante un agente conversacional que usa herramientas SQL
4. **Visualizar estadísticas** en un dashboard de analíticas

Stack: **Python 3.12 · FastAPI · SQLAlchemy · Alembic · Pydantic · OpenAI SDK · LangSmith · Docker · Railway**

---

## Estructura del Curso

### Módulo 0 — Introducción y visión general
- ¿Qué vamos a construir? Demo del resultado final
- Casos de uso reales: tickets de supermercado como datos personales
- Presentación del stack tecnológico
- Cómo leer el repositorio (estructura de directorios)
- Diagrama de arquitectura general

---

### Módulo 1 — FastAPI: el núcleo del backend
**Ficheros:** `src/app/main.py` · `src/app/api/v1/` · `src/app/core/config.py`

- Estructura del proyecto (`src/app/` con api, services, repositories, models, schemas)
- Configuración con variables de entorno (`config.py` con dataclass + dotenv)
- Autenticación simple con OAuth2 Bearer token (`MASTER_KEY`)
- Los cuatro routers: `health`, `extraction`, `dashboard`, `chat`
- Cómo FastAPI genera la documentación automática (Swagger UI)

---

### Módulo 2 — Structured Output con LLM ⭐
**Ficheros:** `src/app/services/llm.py` · `src/app/schemas/extraction.py`

**El módulo clave del curso.** Cómo extraer datos estructurados de una imagen usando solo un LLM, sin depender de ningún servicio externo de OCR.

- El problema: una imagen → datos tipados en Python
- **Pydantic como contrato**: `StructuredExtraction`, `SupermercadoExtraction`, `ProductoCantidadExtraction`
- Construir el prompt con el JSON schema del modelo Pydantic
- Enviar la imagen en base64 al LLM (multimodal)
- `response_format: {"type": "json_object"}` — forzar JSON válido
- Parsear la respuesta con `model.model_validate(json.loads(...))`
- **Retry pattern**: si el modelo devuelve `{}`, se le pide que lo intente de nuevo
- Trazado con LangSmith (`@traceable`)

> **Punto de reflexión**: este patrón funciona con cualquier LLM compatible con la API de OpenAI. Scanéame (Módulo 3) es una alternativa productivizada que hace lo mismo, pero con más garantías para producción.

---

### Módulo 3 — Integración con Scanéame (cliente HTTP asíncrono)
**Ficheros:** `src/app/services/scaneame.py` · `src/app/services/document_extraction.py`

- ¿Qué es Scanéame? API externa para OCR de tickets de supermercado
- `ScaneameClient`: cliente HTTP asíncrono con `httpx`
- Flujo de petición: `POST /v1/process` → `{status: ok|async, job_id}`
- **Polling pattern**: si el trabajo es asíncrono, hacer GET `/v1/jobs/{id}` hasta `done/failed/timeout`
- Jerarquía de excepciones custom (`ScaneameError`, `ScaneameAPIError`, etc.)
- Traducción de errores del servicio externo a errores HTTP de FastAPI
- Comparativa: LLM propio (Módulo 2) vs Scanéame (este módulo)

---

### Módulo 4 — Base de Datos: SQLAlchemy + Alembic
**Ficheros:** `src/app/models/` · `src/app/repositories/` · `alembic/`

- Modelo de datos: `supermercado` → `ticket` → `linea_ticket` ← `producto`
- SQLAlchemy ORM: declarar modelos con tipos Python
- **Patrón Repository**: `SQLDocumentRepository` como capa de acceso a datos
- **Upsert pattern**:
  - `supermercado`: get-or-create por nombre
  - `ticket`: INSERT OR REPLACE por `id_ticket` (PK natural del ticket)
  - `producto`: **fuzzy matching** con `rapidfuzz` para normalizar nombres
  - `linea_ticket`: borra y reinserta al reprocesar un ticket
- Alembic: migraciones como código (`alembic revision --autogenerate`)
- SQLite (dev) → PostgreSQL (prod) sin cambiar código

---

### Módulo 5 — Agente Conversacional con Tool Calling
**Ficheros:** `src/app/services/chat.py` · `src/app/repositories/analytics.py`

- ¿Qué es tool calling / function calling en los LLMs?
- Definir herramientas como `ChatCompletionToolParam`
- Las 6 herramientas SQL del agente:
  - `compare_product_prices` — evolución de precio de un producto
  - `get_spending_summary` — gasto total y por supermercado
  - `get_product_quantities` — cuánto se ha comprado de cada producto
  - `get_purchase_frequency` — frecuencia de compra
  - `get_list_tickets` — lista de tickets recientes
  - `get_ticket_data` — detalle de un ticket concreto
- El **loop del agente**: `for _ in range(8): llm() → tool_call? → ejecutar → volver al llm`
- System prompt con reglas de routing por intención
- LangSmith: trazado de cadenas (`@traceable(run_type="chain")`)

---

### Módulo 6 — Dashboard de Analíticas
**Ficheros:** `src/app/repositories/analytics.py` · `src/app/api/v1/dashboard.py` · `docs/dashboard_mock.html`

- Diseñar las queries de analíticas en SQLAlchemy
- `AnalyticsRepository`: gasto, frecuencia, productos, comparativa de precios
- Contrato del endpoint `GET /api/v1/dashboard/report`
- HTML mock del dashboard (servido directamente desde FastAPI)
- Cómo iterar rápido con datos mock antes de conectar el frontend real

---

### Módulo 7 — Evaluaciones con LangSmith
**Ficheros:** `evals/` · `docs/sesiones/TODO_evaluacion_agente_langsmith.md`

- ¿Por qué evaluar? El problema de los agentes no deterministas
- Crear un dataset de referencia en LangSmith (`luma-spend-agent-v1`)
- Evaluadores deterministas: `correct_tool`, `correct_arguments`, `expected_facts`
- Runner de experimentos: `predict(inputs) → dict`
- Comparar modelos con los mismos datos (Gemma vs OpenAI)
- Métricas: latencia, tokens consumidos, coste, calidad de respuesta
- Ciclo de mejora: analizar traza fallida → mejorar prompt → repetir experimento

---

### Módulo 8 — Despliegue en Railway
**Ficheros:** `Dockerfile` · `.env` · `alembic/`

- `Dockerfile`: `python:3.12-slim`, `uvicorn` como servidor ASGI
- Variables de entorno necesarias: `MASTER_KEY`, `SCANEAME_API_KEY`, `OPENAI_API_KEY`, `DATABASE_URL`, `LANGSMITH_API_KEY`
- PostgreSQL gestionado en Railway: conexión con `DATABASE_URL`
- Ejecutar migraciones de Alembic al desplegar
- Gestionar secretos: nunca subir `.env` al repositorio
- Flujo completo: push a GitHub → Railway detecta cambio → build → deploy

---

## Diagrama de módulos

Ver `docs/diagram.drawio` para los diagramas visuales de:
- Mapa del curso (flujo de aprendizaje)
- Arquitectura general del sistema
- Flujo de Structured Output con LLM
- Agente de chat (loop de herramientas)
- Despliegue en Railway

---

## Sesiones de desarrollo

| Sesión | Fecha | Contenido |
|--------|-------|-----------|
| S1 | Jul 29 | Setup inicial, endpoints básicos |
| S2 | Sep 5 | Dashboard HTML, queries analíticas |
| S3 | Sep 12 | Validaciones: nombre producto (fuzzy), precios |
| S4 | Sep 15 | Evaluaciones con LangSmith |
| S5 | Pendiente | Evaluación del agente completo |
