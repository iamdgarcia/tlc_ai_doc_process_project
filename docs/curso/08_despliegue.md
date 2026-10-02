# Módulo 08 — Despliegue en Railway

**Ficheros:** `Dockerfile` · `.env` · `alembic/`

---

## Dockerfile

```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --app-dir src --host 0.0.0.0 --port ${PORT:-8000}"]
```

**Puntos clave:**
- `python:3.12-slim` — imagen base ligera, sin herramientas de compilación innecesarias
- `PYTHONDONTWRITEBYTECODE` y `PYTHONUNBUFFERED` — buenas prácticas para contenedores
- `pip install` antes de `COPY . .` — aprovecha la caché de capas de Docker: si solo cambia el código (no las dependencias), no se reinstala nada
- `${PORT:-8000}` — Railway inyecta `PORT` dinámicamente; el fallback a `8000` sirve para desarrollo local

---

## Variables de entorno

Railway gestiona los secretos como variables de entorno del servicio. **Nunca van al repositorio.**

| Variable | Descripción |
|----------|-------------|
| `MASTER_KEY` | Clave de autenticación de la API |
| `OPENAI_API_KEY` | Clave de OpenAI (o proveedor compatible) |
| `OPENAI_BASE_URL` | URL base alternativa (Novita, etc.) — opcional |
| `OPENAI_MODEL` | Modelo para extracción (default: `gpt-4.1-mini`) |
| `OPENAI_CHAT_MODEL` | Modelo para el agente (default: `google/gemma-4-31b-it`) |
| `SCANEAME_API_KEY` | Clave de Scanéame |
| `SCANEAME_API_URL` | URL de Scanéame |
| `DATABASE_URL` | Conexión a PostgreSQL (Railway la genera automáticamente) |
| `LANGSMITH_API_KEY` | Clave de LangSmith para trazas |
| `LANGSMITH_PROJECT` | Nombre del proyecto en LangSmith |

---

## PostgreSQL gestionado en Railway

Railway provisiona PostgreSQL automáticamente. La `DATABASE_URL` se inyecta como variable de entorno en el servicio de la API sin configuración manual.

La misma aplicación funciona con SQLite en local y PostgreSQL en Railway porque SQLAlchemy abstrae el motor:

```python
# config.py
database_url: str = os.getenv("DATABASE_URL", "sqlite:///./receipts.db")
```

```python
# db/session.py
engine = create_engine(settings.database_url)
```

---

## Migraciones al arrancar

Al desplegar una nueva versión, hay que aplicar las migraciones de Alembic antes de que empiece a recibir tráfico. La forma más directa es añadirlo al comando de arranque:

```bash
# En el CMD del Dockerfile o como Railway start command:
alembic upgrade head && uvicorn app.main:app --app-dir src --host 0.0.0.0 --port $PORT
```

Alembic es idempotente: si no hay migraciones pendientes, el comando termina inmediatamente sin tocar la base de datos.

---

## Flujo completo de despliegue

![Despliegue en Railway](/docs/deploy.png)


```
1. git push origin main
        ↓
2. Railway detecta el push (webhook de GitHub)
        ↓
3. Railway hace build con el Dockerfile
        ↓
4. Si el build es exitoso, reemplaza el contenedor anterior
        ↓
5. El nuevo contenedor arranca:
   alembic upgrade head  →  uvicorn app.main:app
        ↓
6. La API está disponible en la URL pública de Railway
```

Sin downtime en despliegues normales: Railway levanta el nuevo contenedor antes de matar el anterior.

---

## Desarrollo local

```bash
# Crear entorno virtual
python -m venv venv
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt

# Configurar variables de entorno
cp .env.example .env  # y editar con tus claves

# Aplicar migraciones en SQLite local
alembic upgrade head

# Arrancar en modo desarrollo con recarga automática
uvicorn app.main:app --app-dir src --reload

# Ejecutar tests
pytest tests/
```

---

## Gestionar secretos: reglas básicas

- `.env` está en `.gitignore` — nunca se sube al repositorio
- En Railway, los secretos se gestionan desde el panel de la plataforma
- Para desarrollo en equipo: compartir `.env` de forma segura (1Password, Bitwarden, etc.)
- Para CI: usar las variables de entorno del repositorio de GitHub/GitLab

---

← [07 — Evaluaciones con LangSmith](07_evaluaciones.md)
