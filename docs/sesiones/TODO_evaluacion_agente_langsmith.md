# TODO: evaluacion del agente con LangSmith

## Objetivo de la sesion

Construir una evaluacion reproducible del agente de Luma Spend para responder a
esta pregunta:

> Como sabemos si el agente selecciona la herramienta correcta, utiliza buenos
> argumentos y responde fielmente con los datos de los tickets?

Al terminar la sesion deberiamos tener un dataset de referencia en LangSmith,
un experimento ejecutable y metricas con las que comparar modelos o cambios de
prompt.

## 0. Preparar el entorno

- [ ] Corregir `httpx2` por `httpx` en `requirements.txt`.
- [ ] Revisar y fijar versiones compatibles de FastAPI, Starlette, HTTPX y AnyIO.
- [ ] Investigar por que las pruebas con `TestClient` se bloquean.
- [ ] Conseguir que `pytest -q` complete las 30 pruebas.
- [x] Configurar LangSmith en `.env`:

```dotenv
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_PROJECT=luma-spend-agent-dev
```

- [ ] Comprobar en LangSmith que aparece una traza real del chat.
- [ ] No subir `.env`, claves ni tickets reales al repositorio.

## 1. Definir que significa que el agente funcione

- [ ] Evaluar si selecciona la herramienta correcta.
- [ ] Evaluar si genera argumentos correctos y validos.
- [ ] Evaluar si completa la tarea sin agotar el limite de pasos.
- [ ] Evaluar si la respuesta final esta respaldada por el resultado de las
      herramientas.
- [ ] Registrar numero de pasos, latencia, tokens y coste.
- [ ] Separar los fallos del modelo de los fallos de una herramienta o consulta
      SQL.

## 2. Exponer la trayectoria completa del agente

- [ ] Anadir una traza de tipo `chain` alrededor del ciclo completo del agente.
- [ ] Mantener la traza `llm` de cada llamada al modelo.
- [ ] Trazar cada ejecucion de herramienta como `tool`.
- [ ] Hacer que la ejecucion evaluable devuelva una estructura similar a esta:

```json
{
  "answer": "Respuesta final del agente",
  "tool_calls": [
    {
      "name": "get_spending_summary",
      "arguments": {"days": 365},
      "result": {}
    }
  ],
  "steps": 2,
  "completed": true
}
```

- [ ] Mantener el contrato HTTP actual: la API puede seguir devolviendo solo la
      respuesta que necesita el dashboard.
- [ ] Evitar guardar datos sensibles de tickets en trazas públicas.

## 3. Aislar las ejecuciones

- [ ] Crear un `ChatService` nuevo para cada ejemplo del experimento.
- [ ] Evitar que el historial de una pregunta contamine la siguiente.
- [ ] Sustituir el `ChatService` global compartido por sesiones de conversacion
      aisladas.
- [ ] Abrir y cerrar una sesion SQL independiente para cada ejemplo.
- [ ] Usar `receipt_mock.db` o una base de evaluacion reproducible, nunca datos
      personales reales.

## 4. Permitir cambiar de modelo

- [ ] Inyectar `model` y `client` al construir `ChatService`.
- [ ] Evitar depender exclusivamente de `settings.openai_chat_model` dentro del
      servicio.
- [ ] Registrar proveedor, modelo y version del prompt en los metadatos del
      experimento.
- [ ] Preparar al menos dos configuraciones:
  - [ ] Modelo actual basado en Gemma.
  - [ ] Un modelo OpenAI de referencia.
- [ ] Mantener constantes el dataset, las herramientas, la base de datos y el
      prompt durante la comparacion.

## 5. Crear el dataset de referencia

- [ ] Crear el dataset `luma-spend-agent-v1` en LangSmith.
- [ ] Crear un script idempotente para cargar o actualizar ejemplos.
- [ ] Definir para cada ejemplo:
  - [ ] Pregunta del usuario.
  - [ ] Herramienta o secuencia de herramientas esperada.
  - [ ] Argumentos esperados.
  - [ ] Hechos que deben aparecer en la respuesta.
  - [ ] Categoria y dificultad.
- [ ] Empezar con entre 10 y 15 preguntas.

### Casos iniciales

- [ ] Gasto total y ticket medio en un periodo.
- [ ] Frecuencia de compra.
- [ ] Cantidades compradas de un producto.
- [ ] Evolucion del precio de un producto.
- [ ] Lista de ultimos tickets.
- [ ] Contenido de un ticket concreto.
- [ ] Comparacion de supermercados.
- [ ] Producto que no existe.
- [ ] Periodo ambiguo que requiera una aclaracion o una decision documentada.
- [ ] Pregunta que requiera mas de una herramienta.
- [ ] Pregunta sobre categorias que no existen en el modelo de datos.
- [ ] Pregunta no relacionada con tickets que no deberia activar herramientas.

### Formato orientativo

```json
{
  "inputs": {
    "question": "Cuanto he gastado en los ultimos 12 meses?"
  },
  "outputs": {
    "expected_tools": ["get_spending_summary"],
    "expected_arguments": {"days": 365},
    "expected_facts": ["EUR"]
  },
  "metadata": {
    "category": "spending",
    "difficulty": "easy"
  }
}
```

## 6. Implementar el runner de evaluacion

- [ ] Crear una funcion `predict(inputs: dict) -> dict` compatible con
      `langsmith.evaluation.evaluate`.
- [ ] Crear una sesion de base de datos aislada dentro de `predict`.
- [ ] Construir un agente limpio para cada pregunta.
- [ ] Ejecutar inicialmente con `max_concurrency=1` para facilitar la lectura de
      trazas y evitar ruido de concurrencia con SQLite.
- [ ] Anadir un nombre y descripcion claros a cada experimento.
- [ ] Guardar como metadatos:
  - [ ] Modelo y proveedor.
  - [ ] Version del prompt.
  - [ ] Version del dataset.
  - [ ] Commit de Git evaluado.

## 7. Crear evaluadores deterministas

- [ ] `correct_tool`: compara herramientas elegidas y esperadas.
- [ ] `correct_arguments`: valida argumentos relevantes como `days`, `limit` o
      `product_name`.
- [ ] `completed`: comprueba que el agente termino la tarea.
- [ ] `efficient_trajectory`: penaliza bucles o llamadas innecesarias.
- [ ] `expected_facts`: comprueba que aparecen los hechos esperados.
- [ ] `no_unsupported_numbers`: detecta numeros de la respuesta que no proceden
      de los resultados de las herramientas.
- [ ] Devolver comentarios explicativos junto a cada puntuacion para poder
      depurar los fallos desde LangSmith.

## 8. Ejecutar y comparar experimentos

- [ ] Ejecutar un experimento base con el modelo actual.
- [ ] Revisar manualmente las trazas que fallen.
- [ ] Clasificar cada fallo:
  - [ ] Seleccion de herramienta.
  - [ ] Argumentos.
  - [ ] Consulta o datos.
  - [ ] Interpretacion de resultados.
  - [ ] Redaccion de la respuesta.
- [ ] Aplicar una sola mejora de prompt, descripcion de herramienta o validacion.
- [ ] Repetir el experimento y comparar con el baseline.
- [ ] Ejecutar el mismo dataset con el segundo modelo.
- [ ] Comparar exactitud, latencia, tokens, coste y numero de pasos.

## 9. Evaluaciones avanzadas, si queda tiempo

- [ ] Anadir un evaluador LLM-as-judge para claridad y fidelidad.
- [ ] Ejecutar cada ejemplo varias veces para medir estabilidad.
- [ ] Crear divisiones `development` y `test` en el dataset.
- [ ] Probar un router que envie preguntas sencillas a un modelo barato y reserve
      el modelo mas capaz para preguntas complejas.
- [ ] Evaluar por separado el pipeline de extraccion de tickets con imagenes
      anonimizadas y JSON de referencia.

## Guion sugerido para la clase

- [ ] Mostrar una traza actual y explicar sus limitaciones.
- [ ] Preguntar al grupo que significa que el agente "funcione".
- [ ] Crear tres ejemplos iniciales en LangSmith.
- [ ] Exponer la trayectoria de herramientas en la salida del agente.
- [ ] Implementar `correct_tool` en directo.
- [ ] Ejecutar el primer experimento.
- [ ] Analizar una traza fallida.
- [ ] Mejorar una descripcion de herramienta o el prompt.
- [ ] Repetir el experimento y comprobar si mejora.
- [ ] Comparar dos modelos con el mismo dataset.

## Criterios de cierre de la sesion

- [ ] Existe un dataset versionado en LangSmith.
- [ ] El runner puede repetirse sin cambiar manualmente el codigo.
- [ ] Las trazas muestran agente, llamadas LLM y herramientas.
- [ ] Hay al menos tres evaluadores automaticos.
- [ ] Existe un experimento baseline con resultados visibles.
- [ ] Se ha comparado al menos un cambio de prompt o un segundo modelo.
- [ ] Las decisiones de modelo se apoyan en resultados, latencia y coste, no solo
      en impresiones manuales.

## Entregables

- [ ] Script de creacion/sincronizacion del dataset.
- [ ] Runner de experimentos.
- [ ] Evaluadores deterministas.
- [ ] Dataset `luma-spend-agent-v1` en LangSmith.
- [ ] Enlace o nombre de los experimentos comparados.
- [ ] Resumen corto de resultados y siguiente hipotesis a probar.
