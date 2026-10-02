# Módulo 03 — Integración con Scanéame

**Ficheros:** `src/app/services/scaneame.py` · `src/app/services/document_extraction.py`

---

## ¿Qué es Scanéame?

Scanéame es una API externa especializada en OCR de tickets de supermercado. Recibe una imagen y devuelve los datos del ticket en formato estructurado — el mismo `StructuredExtraction` que construimos manualmente en el Módulo 02, pero como servicio gestionado.

Endpoints que usa:
- `POST /v1/process` — envía el documento, recibe resultado o job_id
- `GET /v1/jobs/{id}` — consulta el estado de un trabajo asíncrono

---

## Cliente HTTP asíncrono con httpx

`ScaneameClient` encapsula toda la comunicación con la API externa:

```python
class ScaneameClient:
    async def process_document(self, document_bytes: bytes, content_type: str) -> object:
        input_value = _document_input(document_bytes, content_type)  # base64 o texto

        async with httpx.AsyncClient(headers=..., timeout=...) as client:
            response = await client.post(
                self._api_url,
                json={"endpoint": self._endpoint, "input": input_value},
            )
            body = self._parse_response(response)

            if body["status"] == "ok":
                return body["result"]           # resultado síncrono
            if body["status"] == "async":
                return await self._wait_for_job(client, body["job_id"])  # polling
```

**Por qué `httpx` y no `requests`**: FastAPI es async. `requests` es bloqueante y congestionaría el event loop. `httpx` tiene la misma API pero soporta `async/await`.

---

## Polling pattern para trabajos asíncronos

Cuando Scanéame devuelve `status: async`, el procesamiento del ticket puede tardar varios segundos. Hay que consultar periódicamente:

```python
async def _wait_for_job(self, client, job_id: str) -> object:
    deadline = monotonic() + self._processing_timeout_seconds

    while monotonic() < deadline:
        await asyncio.sleep(self._poll_interval_seconds)
        response = await client.get(f"/v1/jobs/{job_id}")
        body = self._parse_response(response)

        match body["status"]:
            case "queued" | "processing":
                continue                          # seguir esperando
            case "failed":
                raise ScaneameAPIError(502, body.get("message", ""))
            case "done":
                return body["result"]["result"]   # resultado final

    raise ScaneameProcessingTimeout(...)
```

**Punto clave**: el polling tiene un deadline fijo (`processing_timeout_seconds`). Si Scanéame tarda más de ese tiempo, lanzamos `ScaneameProcessingTimeout` y FastAPI devuelve `504 Gateway Timeout`.

---

## Jerarquía de excepciones custom

Las excepciones permiten traducir errores del servicio externo en respuestas HTTP coherentes:

```
ScaneameError  (base)
├── ScaneameConfigurationError  →  500 (API key no configurada)
├── ScaneameInputError          →  422 (imagen no válida)
├── ScaneameProtocolError       →  502 (respuesta inesperada de Scanéame)
├── ScaneameProcessingTimeout   →  504 (tardó demasiado)
└── ScaneameAPIError(status, detail)  →  varía según el status HTTP de Scanéame
```

```python
# services/document_extraction.py — traducción de excepciones
try:
    extracted = await extract_ticket(document_bytes, content_type)
except ScaneameProcessingTimeout:
    raise HTTPException(504, "Scanéame tardó demasiado.")
except ScaneameAPIError as exc:
    if exc.status_code in {401, 403}:
        raise HTTPException(502, "Scanéame rechazó la API key.")
    ...
```

Este patrón de traducción de excepciones mantiene los detalles internos del servicio externo separados del contrato HTTP de nuestra API.

---

## Validación de la respuesta

La respuesta de Scanéame puede llegar en su formato nativo o ya como `StructuredExtraction`. La función `_validate_ticket_result` maneja ambos casos:

```python
def _validate_ticket_result(raw_result: object) -> StructuredExtraction:
    # Intenta primero validar directamente como StructuredExtraction
    try:
        return StructuredExtraction.model_validate(raw_result)
    except ValidationError:
        pass

    # Si no, convierte desde el formato nativo de Scanéame
    ticket = ScaneameTicketResult.model_validate(raw_result)
    return StructuredExtraction(
        id_ticket=ticket.id_ticket,
        supermercado=SupermercadoExtraction(nombre_supermercado=ticket.supermercado),
        dia=ticket.fecha_compra,
        ...
    )
```

---

## Comparativa: LLM propio vs Scanéame

| | Módulo 02 (LLM propio) | Módulo 03 (Scanéame) |
|--|------------------------|----------------------|
| Control | Total sobre el prompt | Ninguno |
| Coste | Paga por token | Precio por ticket |
| Latencia | Variable según modelo | Gestionada por Scanéame |
| Mantenimiento | Tú ajustas el prompt | Scanéame actualiza |
| Privacidad | Tus datos van a OpenAI | Tus datos van a Scanéame |
| Adecuado para | Prototipos, control total | Producción estable |

En producción, Scanéame es la opción por defecto porque abstrae la complejidad del OCR. El Módulo 02 sirve para entender qué hay debajo y como fallback cuando no hay conectividad con Scanéame.

---

## Siguiente módulo

→ [04 — Base de datos: SQLAlchemy + Alembic](04_base_de_datos.md)
