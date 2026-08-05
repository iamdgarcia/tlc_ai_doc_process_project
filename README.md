# Process Documents API

Base structure for a FastAPI application using the `src` layout.

## Endpoints

- `GET /api/v1/health`: health check.
- `POST /api/v1/documents/extract`: receives an image or PDF and returns a structured Pydantic response.

## Run locally

```bash
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --app-dir src
```

## Environment

- `OPENAI_API_KEY`: required to call the LLM.
- `OPENAI_MODEL`: optional, defaults to `gpt-4.1-mini`.
