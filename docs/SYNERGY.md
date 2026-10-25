# Luma Spend ↔ DocProc SaaS

Dos repos, dos roles, un mismo dominio: extraer datos estructurados de documentos.

## Qué es cada uno

- **Luma Spend** (este repo) es el proyecto de muestra visible para humanos: un curso
  completo (`docs/curso/`) donde se construye, paso a paso, una API que extrae tickets
  de supermercado, los almacena y responde preguntas sobre ellos. Un learner puede
  desplegarlo en Railway en unos 30 minutos siguiendo el módulo 08.
- **DocProc SaaS** ([github.com/iamdgarcia/document_process_saas](https://github.com/iamdgarcia/document_process_saas),
  nombre público: Scanéame) es el producto multi-tenant que hace lo mismo como servicio:
  endpoints de extracción definidos por descripción + ejemplos, con gobernanza (claves
  `sk_live_*` con scope por endpoint), billing con créditos, control dataset, versionado
  de esquemas y rollback.

## Convergencias concretas

1. **Luma Spend es el worked example.** Es la referencia didáctica de lo que DocProc
   vende gestionado: mismo contrato de extracción (Pydantic → JSON estructurado),
   mismos patrones de polling de jobs asíncronos, mismo despliegue en Railway.
2. **El esquema de ticket es el tipo de endpoint que DocProc sintetiza.** Las tablas
   `supermercado / ticket / producto / linea_ticket` y el schema `StructuredExtraction`
   (`src/app/schemas/extraction.py`) son exactamente lo que en DocProc se define como
   un endpoint `tickets` desde descripción + ejemplos, sin escribir el código del
   extractor a mano.
3. **Infra compartida.** Ambos hablan con gateways compatibles con OpenAI
   (`OPENAI_API_KEY` / `OPENAI_BASE_URL`), despliegan en Railway con migraciones
   Alembic al arranque, y usan structured output como contrato (no parsing de prosa).

## El puente en código

Las variables `SCANEAME_*` de este repo (`src/app/core/config.py`) apuntan al SaaS:

| Variable en Luma Spend | Equivalente en DocProc |
|---|---|
| `SCANEAME_API_KEY` | API key `sk_live_*` del data plane |
| `SCANEAME_ENDPOINT` | slug del endpoint (`tickets`) |
| `SCANEAME_API_URL` | URL del servicio web desplegado |
| `SCANEAME_REQUEST_TIMEOUT_SECONDS` | ruta síncrona de `/v1/process` |
| `SCANEAME_PROCESSING_TIMEOUT_SECONDS` / `SCANEAME_POLL_INTERVAL_SECONDS` | ruta asíncrona (`/v1/jobs/:id`) |

Sin `SCANEAME_API_KEY`, Luma Spend llama al LLM directamente: el SaaS es el camino
gestionado; la llamada directa es el camino de desarrollo.

## Regla de acoplamiento

Si cambian los campos de `StructuredExtraction`, la configuración del endpoint `tickets`
en DocProc debe actualizarse y redesplegarse (esquema + ejemplos). Cada repo es dueño
de su lado: este del contrato didáctico, el SaaS del producto.
