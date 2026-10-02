# Luma Spend — Curso Completo
> Construye una API de análisis de tickets de supermercado con FastAPI, LLMs y Railway

**Luma Spend** es una API REST que permite:
1. **Subir un ticket de supermercado** (imagen o PDF) y extraer sus datos de forma estructurada usando un LLM
2. **Almacenar los datos** en una base de datos relacional (SQLite en dev, PostgreSQL en prod)
3. **Consultar el historial de compras** mediante un agente conversacional que usa herramientas SQL
4. **Visualizar estadísticas** en un dashboard de analíticas

Stack: **Python 3.12 · FastAPI · SQLAlchemy · Alembic · Pydantic · OpenAI SDK · LangSmith · Docker · Railway**

---

## Módulos

| # | Título | Fichero |
|---|--------|---------|
| 00 | Introducción y visión general | [00_introduccion.md](00_introduccion.md) |
| 01 | FastAPI: el núcleo del backend | [01_fastapi.md](01_fastapi.md) |
| 02 ⭐ | Structured Output con LLM | [02_structured_output.md](02_structured_output.md) |
| 03 | Integración con Scanéame | [03_scaneame.md](03_scaneame.md) |
| 04 | Base de datos: SQLAlchemy + Alembic | [04_base_de_datos.md](04_base_de_datos.md) |
| 05 | Agente Conversacional con Tool Calling | [05_agente.md](05_agente.md) |
| 06 | Dashboard de Analíticas | [06_dashboard.md](06_dashboard.md) |
| 07 | Evaluaciones con LangSmith | [07_evaluaciones.md](07_evaluaciones.md) |
| 08 | Despliegue en Railway | [08_despliegue.md](08_despliegue.md) |

---

## Diagramas

Ver [`../diagram.drawio`](../diagram.drawio):
- **0. Mapa del Curso** — flujo de aprendizaje entre módulos
- **1. Arquitectura General** — sistema completo con logos de tecnologías
- **2. Structured Output LLM** — imagen → datos tipados en Python
- **3. Agente de Chat** — loop de herramientas
- **4. Modelo de Datos** — ERD de las 4 tablas
- **5. Despliegue Railway** — infraestructura

---

## Sesiones en directo

| # | Fecha | Título | Módulos |
|---|-------|--------|--------|
| 1 | Jul 19 | [Setup de stream y estructura inicial de la API](https://iamdgarcia.substack.com/p/probamos-stream-desde-obs-y-montamos) | 00, 01, 02 |
| 2 | Jul 26 | [Extracción de documentos con IA (Parte 2)](https://iamdgarcia.substack.com/p/creando-una-app-para-procesar-documentos) | 02, 03 |
| 3 | Ago 2 | [Dashboard de explotación con Claude Code](https://iamdgarcia.substack.com/p/desarrollando-una-app-para-procesar) | 06 |
| 4 | Ago 9 | [Primeras validaciones: duplicados y supermercados](https://iamdgarcia.substack.com/p/creando-una-app-para-procesar-documentos-263) | 04 |
| 5 | Ago 16 | [Comparaciones semánticas y fuzzy matching](https://iamdgarcia.substack.com/p/creando-una-app-para-procesar-documentos-714) | 04, 05 |
| 6 | Ago 23 | [Desplegamos el proyecto en Railway](https://iamdgarcia.substack.com/p/creando-una-app-para-procesar-documentos-411) | 08 |

Todas las sesiones: [iamdgarcia.substack.com/s/directos](https://iamdgarcia.substack.com/s/directos)
