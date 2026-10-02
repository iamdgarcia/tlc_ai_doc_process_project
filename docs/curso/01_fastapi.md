# Módulo 01 — FastAPI: el núcleo del backend

**Ficheros:** `src/app/main.py` · `src/app/api/v1/` · `src/app/core/config.py`

---

## Estructura del proyecto

El proyecto sigue la convención de separar responsabilidades en capas:

```
src/app/
├── main.py          # App FastAPI + auth + rutas raíz
├── core/config.py   # Settings (variables de entorno)
├── api/v1/
│   ├── router.py    # Agrega los 4 routers
│   ├── health.py    # GET /health
│   ├── extraction.py # POST /documents/extract
│   ├── dashboard.py  # GET /dashboard/report
│   └── chat.py       # POST /chat
├── services/        # Lógica de negocio
├── repositories/    # Acceso a datos
├── models/          # ORM SQLAlchemy
└── schemas/         # Pydantic (contratos de entrada/salida)
```

---

## Configuración con variables de entorno

`config.py` usa un `dataclass` frozen con `os.getenv` y `dotenv`:

```python
@dataclass(frozen=True)
class Settings:
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./receipts.db")
    scaneame_api_key: str | None = os.getenv("SCANEAME_API_KEY")
    ...

settings = Settings()
```

**Por qué dataclass y no Pydantic Settings**: es más ligero y suficiente cuando los valores son solo strings de entorno. Pydantic BaseSettings añadiría coerciones y validaciones que aquí no necesitamos.

---

## Autenticación con Bearer token

Autenticación simple de un solo secreto compartido (`MASTER_KEY`):

```python
# POST /token — devuelve el token (es la propia clave)
@app.post("/token")
async def login(password: Annotated[str, Form()]):
    if password != MASTER_KEY:
        raise HTTPException(status_code=401)
    return {"access_token": password, "token_type": "bearer"}

# Dependency que protege todas las rutas /api/v1/*
async def verify_token(token: Annotated[str, Depends(oauth2_scheme)]):
    if token != MASTER_KEY:
        raise HTTPException(status_code=401)
```

```python
# Aplicado al router completo en main.py
app.include_router(v1_router, prefix="/api/v1", dependencies=[Depends(verify_token)])
```

**Punto clave**: `dependencies=[Depends(verify_token)]` en `include_router` aplica la autenticación a *todos* los endpoints del router de una vez, sin decorar cada función individualmente.

---

## Los cuatro endpoints principales

| Método | Ruta | Qué hace |
|--------|------|---------|
| `GET` | `/api/v1/health` | Comprueba que la API está viva |
| `POST` | `/api/v1/documents/extract` | Sube una imagen/PDF y extrae el ticket |
| `POST` | `/api/v1/documents/batch` | Sube varios tickets a la vez |
| `GET` | `/api/v1/dashboard/report` | Devuelve datos de analíticas |
| `POST` | `/api/v1/chat` | Pregunta al agente en lenguaje natural |

---

## Dashboard HTML integrado

La ruta raíz `/` sirve el `dashboard_mock.html` directamente desde FastAPI:

```python
_DASHBOARD_HTML = Path(__file__).resolve().parents[2] / "docs" / "dashboard_mock.html"

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard_view() -> HTMLResponse:
    return HTMLResponse(_DASHBOARD_HTML.read_text(encoding="utf-8"))
```

`include_in_schema=False` lo excluye del Swagger UI — es una ruta de conveniencia, no parte del contrato de la API.

---

## Documentación automática

FastAPI genera Swagger UI en `/docs` y ReDoc en `/redoc` sin configuración adicional. Los schemas de Pydantic que devuelve cada endpoint se reflejan automáticamente.

---

## Siguiente módulo

→ [02 — Structured Output con LLM](02_structured_output.md)
