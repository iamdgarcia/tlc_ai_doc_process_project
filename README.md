# Process Documents API

Base structure for a FastAPI application using the `src` layout.

## Endpoints

- `GET /api/v1/health`: health check.
- `POST /api/v1/documents/extract`: receives an image or text-based PDF, extracts it through Scanéame, stores it, and returns a structured Pydantic response.

## Run locally

```bash
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --app-dir src
```

## Environment

- `SCANEAME_API_KEY`: required for document extraction.
- `SCANEAME_API_URL`: optional, defaults to `https://scaneame.iamdgarcia.com/v1/process`.
- `SCANEAME_ENDPOINT`: optional, defaults to `tickets`.
- `SCANEAME_REQUEST_TIMEOUT_SECONDS`: optional timeout for each HTTP request, defaults to `60`.
- `SCANEAME_PROCESSING_TIMEOUT_SECONDS`: optional overall timeout while polling asynchronous jobs, defaults to `180`.
- `SCANEAME_POLL_INTERVAL_SECONDS`: optional job polling interval, defaults to `1`.

Image uploads are sent as `data:<mime>;base64,...`. Text-based PDFs are converted to text before
calling Scanéame; scanned PDFs must first be converted to images.

`OPENAI_API_KEY` and the OpenAI-compatible model settings are still used by the chat service.
