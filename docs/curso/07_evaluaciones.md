# Módulo 07 — Evaluaciones con LangSmith

**Ficheros:** `evals/` · `docs/sesiones/TODO_evaluacion_agente_langsmith.md`

---

## El problema de los agentes no deterministas

Un agente LLM puede responder bien el 90% de las veces y fallar el 10% de maneras impredecibles. Sin evaluaciones sistemáticas:

- No sabes si un cambio de prompt mejoró o empeoró la calidad
- No puedes comparar dos modelos de forma objetiva
- Los fallos aparecen en producción, no en desarrollo

La pregunta que queremos responder: **¿cómo sabemos si el agente selecciona la herramienta correcta y responde fielmente con los datos de los tickets?**

---

## Dataset de referencia

Un dataset es una colección de preguntas con las respuestas esperadas. Se crea una vez y se reutiliza para todos los experimentos:

```json
{
  "inputs": {
    "question": "¿Cuánto he gastado en los últimos 12 meses?"
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

El dataset `luma-spend-agent-v1` cubre:
- Gasto total y ticket medio en un periodo
- Frecuencia de compra
- Cantidades compradas de un producto
- Evolución del precio de un producto
- Lista de últimos tickets
- Contenido de un ticket concreto
- Comparación de supermercados
- Producto que no existe en la base de datos
- Pregunta no relacionada con tickets (no debe activar herramientas)

---

## Exponer la trayectoria del agente

El agente necesita devolver información sobre cómo llegó a su respuesta, no solo el texto final:

```python
def chat_for_eval(self, question: str) -> dict:
    self.messages = []
    answer = self.chat(question)
    return {
        "answer": answer,
        "tool_calls": self._extract_tool_calls_from_messages(),
        "steps": sum(1 for m in self.messages if m.get("role") == "assistant"),
        "completed": "No he podido completar" not in answer,
    }
```

```python
# evals/run_eval.py
def predict(inputs: dict) -> dict:
    session = SessionLocal()
    service = ChatService(session=session)
    return service.chat_for_eval(inputs["question"])
```

---

## Evaluadores deterministas

```python
# evals/evaluators.py

def correct_tool(run, example) -> dict:
    """¿El agente llamó a las herramientas esperadas?"""
    expected = set(example.outputs.get("expected_tools", []))
    actual = {tc["name"] for tc in run.outputs.get("tool_calls", [])}
    score = 1 if expected.issubset(actual) else 0
    return {"key": "correct_tool", "score": score}

def correct_arguments(run, example) -> dict:
    """¿Los argumentos relevantes son correctos?"""
    expected_args = example.outputs.get("expected_arguments", {})
    tool_calls = run.outputs.get("tool_calls", [])
    for tc in tool_calls:
        if all(tc["arguments"].get(k) == v for k, v in expected_args.items()):
            return {"key": "correct_arguments", "score": 1}
    return {"key": "correct_arguments", "score": 0}

def expected_facts(run, example) -> dict:
    """¿Aparecen en la respuesta los hechos esperados?"""
    answer = run.outputs.get("answer", "")
    facts = example.outputs.get("expected_facts", [])
    score = sum(1 for f in facts if f in answer) / len(facts) if facts else 1
    return {"key": "expected_facts", "score": score}
```

---

## Ejecutar un experimento

```python
from langsmith.evaluation import evaluate

results = evaluate(
    predict,
    data="luma-spend-agent-v1",
    evaluators=[correct_tool, correct_arguments, expected_facts],
    experiment_prefix="gemma-4-31b-baseline",
    metadata={
        "model": "google/gemma-4-31b-it",
        "prompt_version": "v1",
    },
)
```

LangSmith guarda los resultados y permite comparar experimentos visualmente.

---

## Ciclo de mejora

```
1. Ejecutar experimento base
2. Ver en LangSmith qué preguntas fallaron
3. Clasificar el fallo:
   - ¿Herramienta equivocada? → mejorar descripción de la herramienta
   - ¿Argumentos incorrectos? → añadir ejemplo en el system prompt
   - ¿Respuesta imprecisa? → ajustar el prompt final
4. Aplicar UNA mejora
5. Repetir el experimento y comparar métricas
```

La clave es cambiar **una sola cosa** entre experimentos. Si cambias tres cosas a la vez, no sabes cuál funcionó.

---

## Comparar modelos

El mismo dataset y los mismos evaluadores se ejecutan con diferentes modelos:

```
Experimento A: google/gemma-4-31b-it
Experimento B: gpt-4o-mini

Métricas comparadas:
- correct_tool: ¿selecciona la herramienta correcta?
- correct_arguments: ¿los argumentos son válidos?
- expected_facts: ¿los hechos aparecen en la respuesta?
- Latencia media
- Tokens consumidos
- Coste por pregunta
```

La decisión de modelo se apoya en datos, no en impresiones subjetivas.

---

## Siguiente módulo

→ [08 — Despliegue en Railway](08_despliegue.md)
