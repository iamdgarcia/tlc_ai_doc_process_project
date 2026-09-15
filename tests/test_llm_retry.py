from types import SimpleNamespace

from app.schemas.extraction import StructuredExtraction
from app.services.llm import StructuredLLMInput, llm_as_structured_output


def test_structured_extraction_retries_an_empty_object(monkeypatch) -> None:
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGSMITH_TRACING_V2", "false")
    responses = iter(
        [
            "{}",
            """{
                "id_ticket": "T-RETRY",
                "supermercado": {"nombre_supermercado": "mercadona"},
                "dia": "2026-05-26",
                "hora": "12:00",
                "total": 10.5,
                "productos": []
            }""",
        ]
    )
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=next(responses)))]
        )

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    monkeypatch.setattr("app.services.llm._get_wrapped_client", lambda: client)

    result = llm_as_structured_output(
        payload=StructuredLLMInput(
            document_name="ticket.jpg",
            content_type="image/jpeg",
            document_bytes=b"image",
            lista_supermercados=["mercadona"],
        ),
        response_model=StructuredExtraction,
    )

    assert result.id_ticket == "T-RETRY"
    assert len(calls) == 2
    assert calls[0]["temperature"] == 0
    assert "respuesta anterior" in calls[1]["messages"][-1]["content"].lower()
