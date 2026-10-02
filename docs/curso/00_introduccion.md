# Módulo 00 — Introducción y Visión General

## ¿Qué vamos a construir?

**Luma Spend** es una API REST que convierte fotos de tickets de supermercado en datos estructurados y los hace consultables mediante lenguaje natural.

El flujo completo de usuario:
1. El usuario fotografía su ticket en el supermercado
2. Sube la imagen a la API (o la envía por Telegram)
3. La API extrae los productos, precios y fecha usando un LLM
4. Los datos quedan guardados en base de datos
5. El usuario puede preguntar cosas como: *"¿Cuánto gasté en leche el último año?"*

---

## Casos de uso reales

- **Control de gasto personal**: saber en qué supermercado sale más barato el aceite
- **Análisis de hábitos**: frecuencia de compra, evolución de precios
- **Datos propios**: alternativa a apps de fidelización que se quedan tus datos

---

## Stack tecnológico

| Capa | Tecnología | Para qué |
|------|-----------|---------|
| API | **FastAPI** | Servidor HTTP, validación, docs automáticas |
| LLM | **OpenAI SDK** | Extracción estructurada de tickets |
| OCR externo | **Scanéame** | Alternativa productivizada al LLM propio |
| Base de datos | **SQLAlchemy + Alembic** | ORM y migraciones |
| Validación | **Pydantic** | Contrato de datos entre LLM y base de datos |
| Trazas | **LangSmith** | Observabilidad del agente y evaluaciones |
| Despliegue | **Railway + Docker** | Plataforma cloud con PostgreSQL gestionado |

---

## Estructura del repositorio

```
process_documents_api/
├── src/app/
│   ├── main.py              # Punto de entrada FastAPI
│   ├── core/config.py       # Variables de entorno
│   ├── api/v1/              # Routers: health, extraction, dashboard, chat
│   ├── services/            # Lógica de negocio: llm, scaneame, chat
│   ├── repositories/        # Acceso a datos: documents, analytics, dashboard
│   ├── models/              # ORM: supermercado, ticket, producto, linea_ticket
│   └── schemas/             # Pydantic: extraction, dashboard, chat
├── alembic/                 # Migraciones de base de datos
├── evals/                   # Evaluaciones con LangSmith
├── tests/                   # Tests
├── docs/curso/              # ← estás aquí
├── Dockerfile
└── requirements.txt
```

---

## Diagrama de arquitectura

![Arquitectura general](../general.png)

> Exportado de la pestaña **"1. Arquitectura General"** de `docs/diagram.drawio`.

---

## Sesiones en directo

Este proyecto se construyó en 6 sesiones en directo en Substack:

| # | Fecha | Título | Módulos |
|---|-------|--------|--------|
| 1 | Jul 19 | [Setup de stream y estructura inicial de la API](https://iamdgarcia.substack.com/p/probamos-stream-desde-obs-y-montamos) | 00, 01, 02 |
| 2 | Jul 26 | [Extracción de documentos con IA (Parte 2)](https://iamdgarcia.substack.com/p/creando-una-app-para-procesar-documentos) | 02, 03 |
| 3 | Ago 2 | [Dashboard de explotación con Claude Code](https://iamdgarcia.substack.com/p/desarrollando-una-app-para-procesar) | 06 |
| 4 | Ago 9 | [Primeras validaciones: duplicados y supermercados](https://iamdgarcia.substack.com/p/creando-una-app-para-procesar-documentos-263) | 04 |
| 5 | Ago 16 | [Comparaciones semánticas y fuzzy matching](https://iamdgarcia.substack.com/p/creando-una-app-para-procesar-documentos-714) | 04, 05 |
| 6 | Ago 23 | [Desplegamos el proyecto en Railway](https://iamdgarcia.substack.com/p/creando-una-app-para-procesar-documentos-411) | 08 |

Todas las sesiones: [iamdgarcia.substack.com/s/directos](https://iamdgarcia.substack.com/s/directos)

---

## Siguiente módulo

→ [01 — FastAPI: el núcleo del backend](01_fastapi.md)
