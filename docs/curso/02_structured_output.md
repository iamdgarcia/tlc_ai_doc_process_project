# Módulo 02 ⭐ — Structured Output con LLM
![so](../structured_output.png)
**Ficheros:** `src/app/services/llm.py` · `src/app/schemas/extraction.py`

> El módulo más importante del curso. Este patrón es aplicable a cualquier dominio donde necesites convertir un documento no estructurado (imagen, PDF, texto) en datos tipados en Python.

---

## El problema

Tienes una foto de un ticket de supermercado. Necesitas:

```
🧾 imagen JPG  →  {"supermercado": "Mercadona", "productos": [...], "total": 34.50}
```

Sin este patrón, tendrías que:
- Integrar un OCR de terceros (Tesseract, Google Vision...)
- Parsear el texto resultante con expresiones regulares
- Gestionar los miles de formatos distintos de cada supermercado

Con LLMs modernos multimodales, el problema se resuelve en ~50 líneas.

---

## El contrato: Pydantic como esquema de salida

Primero defines **qué datos quieres extraer** como modelos Pydantic:

```python
# schemas/extraction.py

class SupermercadoExtraction(BaseModel):
    nombre_supermercado: str | None = Field(default=None)

class ProductoCantidadExtraction(BaseModel):
    nombre_producto: str | None = Field(default=None)
    cantidad: str | float | int | None = Field(default=None)
    precio: float | None = Field(default=None)

    @model_validator(mode="after")
    def _coerce_cantidad_to_string(self) -> ProductoCantidadExtraction:
        # El LLM puede devolver 2 o "2kg" — normalizamos a str
        if isinstance(self.cantidad, (int, float)):
            self.cantidad = str(self.cantidad)
        return self

class StructuredExtraction(BaseModel):
    id_ticket: str | None = Field(default=None)
    supermercado: SupermercadoExtraction
    dia: str | None = Field(default=None)   # YYYY-MM-DD
    hora: str | None = Field(default=None)  # HH:MM
    total: float | None = Field(default=None)
    productos: list[ProductoCantidadExtraction]
```

**Por qué `| None` en todos los campos**: los tickets del mundo real son imperfectos. El LLM puede no ver el total, o la fecha puede estar cortada. `None` es un valor válido; la validación de obligatoriedad se hace *después* de la extracción, en `document_extraction.py`.

---

## Construir el prompt con el JSON schema

El truco central: incluir el JSON schema de Pydantic en el prompt para que el LLM sepa exactamente qué estructura devolver.

```python
# services/llm.py

def _build_document_context(payload, response_model):
    # Pydantic genera el JSON schema automáticamente
    schema = json.dumps(response_model.model_json_schema(), ensure_ascii=False, indent=2)

    instructions = (
        "Extrae la información estructurada del documento y devuelve SOLO JSON válido "
        "con exactamente los campos definidos en este esquema:\n\n"
        f"{schema}\n\n"
        "Reglas estrictas:\n"
        "- Si un campo no está disponible, usa null.\n"
        "- nombre_producto: solo el nombre en minúsculas, sin cantidades.\n"
        "- cantidad: extrae cantidad/unidad separada del nombre.\n"
        "- dia en formato ISO YYYY-MM-DD, hora en formato HH:MM."
    )
```

---

## Enviar la imagen al LLM (multimodal)

Para imágenes, la imagen va en base64 dentro del mensaje de usuario:

```python
if content_type.startswith("image/"):
    encoded = base64.b64encode(document_bytes).decode("utf-8")
    image_url = f"data:{content_type};base64,{encoded}"
    content = [
        {"type": "text", "text": instructions},
        {"type": "image_url", "image_url": {"url": image_url}},
    ]
```

Para PDFs, primero se extrae el texto con `pypdf` y se manda como texto plano (los PDFs de texto no necesitan visión multimodal).

---

## Forzar JSON válido y validar con Pydantic

```python
@traceable(name="Extraction Pipeline")
def llm_as_structured_output(*, payload, response_model):
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=messages,
        temperature=0,
        response_format={"type": "json_object"},  # ← fuerza JSON válido
    )
    raw = response.choices[0].message.content
    parsed = json.loads(raw)
    return response_model.model_validate(parsed)   # ← Pydantic valida y tipifica
```

`response_format: {"type": "json_object"}` garantiza que el modelo devuelva JSON parseable. Sin esto, el modelo puede añadir texto antes o después del JSON.

---

## Retry pattern

Si el modelo devuelve un objeto vacío `{}`, se le pide que lo intente de nuevo con el contexto del error:

```python
for attempt in range(2):
    response = client.chat.completions.create(...)
    try:
        return response_model.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError):
        if attempt == 0:
            # Añadir el fallo al historial y pedir que reintente
            messages.extend([
                {"role": "assistant", "content": raw or "{}"},
                {"role": "user", "content": "La respuesta está vacía. Vuelve a examinar el ticket."},
            ])
```

Dos intentos son suficientes. Si falla dos veces, el problema es la calidad de la imagen o el modelo, no el código.

---

## Trazado con LangSmith

`@traceable(name="Extraction Pipeline")` registra automáticamente cada llamada en LangSmith: prompt, respuesta, latencia y tokens consumidos. Sin tocar el código de lógica.

---

## ¿Y Scanéame?

Scanéame (Módulo 03) hace exactamente lo mismo, pero como servicio gestionado:
- Tú envías la imagen
- Ellos ejecutan el LLM y devuelven el mismo `StructuredExtraction`
- Sin gestionar claves de OpenAI, sin preocuparte por la latencia del modelo

Es la versión productivizada de este módulo. **Entender el Módulo 02 te da la base para entender qué hace Scanéame por debajo.**

---

## Siguiente módulo

→ [03 — Integración con Scanéame](03_scaneame.md)
