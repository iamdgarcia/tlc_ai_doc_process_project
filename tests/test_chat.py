"""Chat robustness: per-request state, tool-call guard, result caps."""

from __future__ import annotations

import datetime
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.chat import get_chat_service
from app.main import app
from app.models import Base, LineaTicket, Producto, Supermercado, Ticket
from app.repositories.analytics import AnalyticsRepository
from app.services.chat import ChatService


class EchoLLMClient:
    """Fake LLM: responde con el último mensaje del usuario, sin tools."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        messages = kwargs["messages"]
        last_user = next(
            m["content"] for m in reversed(messages) if m.get("role") == "user"
        )

        def model_dump(exclude_none: bool = True) -> dict:
            return {"role": "assistant", "content": last_user}

        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=last_user, tool_calls=None, model_dump=model_dump
                    )
                )
            ]
        )

    @property
    def chat(self):
        return SimpleNamespace(completions=SimpleNamespace(create=self._create))


def _raw_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


def test_malformed_tool_arguments_return_error_to_model_instead_of_500() -> None:
    service = ChatService(session=Session(_raw_engine()), client=object())

    result = service._handle_tool_call("get_list_tickets", {"limit": "todas"})

    assert "error" in result
    assert "ValueError" in result["error"]


def test_tool_error_is_serializable_into_the_conversation() -> None:
    service = ChatService(session=Session(_raw_engine()), client=object())

    result = service._handle_tool_call("get_ticket_data", {"ticket_id": None})

    json.dumps(result, ensure_ascii=False)  # el resultado viaja json.dumps al modelo


def test_price_history_is_capped_before_reaching_the_llm_context() -> None:
    engine = _raw_engine()
    with Session(engine) as session:
        store = Supermercado(nombre="mercadona")
        product = Producto(nombre="pan")
        session.add_all([store, product])
        session.flush()
        for i in range(250):
            session.add(
                Ticket(
                    id_ticket=f"T-{i}",
                    supermercado=store,
                    dia=datetime.date(2026, 1, 1) + datetime.timedelta(days=i),
                    hora=datetime.time(10, 0),
                    total=10,
                )
            )
            session.add(
                LineaTicket(
                    id_ticket=f"T-{i}",
                    id_producto=product.id_producto,
                    precio=1.0,
                )
            )
        session.commit()

        result = AnalyticsRepository(session).compare_product_prices("pan")

    assert result["observations"] == 200
    assert len(result["history"]) == 200


def test_concurrent_chat_requests_do_not_share_conversation(seeded_engine) -> None:
    TestingSessionLocal = sessionmaker(bind=seeded_engine)

    def make_service():
        # Un ChatService por petición: su propia conversación y su propia sesión.
        return ChatService(session=TestingSessionLocal(), client=EchoLLMClient())

    app.dependency_overrides[get_chat_service] = make_service
    try:
        def send(message: str) -> str:
            with patch("app.main.MASTER_KEY", "test-master-key"):
                client = TestClient(app)
                response = client.post(
                    "/api/v1/agent/chat",
                    json={"message": message},
                    headers={"Authorization": "Bearer test-master-key"},
                )
            assert response.status_code == 200
            return response.json()["response"]

        with ThreadPoolExecutor(max_workers=2) as pool:
            answers = list(pool.map(send, ["pregunta-A", "pregunta-B"]))
    finally:
        app.dependency_overrides.pop(get_chat_service, None)

    assert "pregunta-A" in answers[0] and "pregunta-B" not in answers[0]
    assert "pregunta-B" in answers[1] and "pregunta-A" not in answers[1]


def test_chat_endpoint_runs_the_llm_call_off_the_event_loop(seeded_engine) -> None:
    """La dependencia async resuelve en el event loop; el LLM síncrono no puede compartir hilo."""
    threads: dict[str, int] = {}
    TestingSessionLocal = sessionmaker(bind=seeded_engine)

    class ThreadRecordingClient(EchoLLMClient):
        def _create(self, **kwargs):
            threads["llm"] = threading.get_ident()
            return super()._create(**kwargs)

    async def override():
        threads["event_loop"] = threading.get_ident()
        return ChatService(session=TestingSessionLocal(), client=ThreadRecordingClient())

    app.dependency_overrides[get_chat_service] = override
    try:
        with patch("app.main.MASTER_KEY", "test-master-key"):
            client = TestClient(app)
            response = client.post(
                "/api/v1/agent/chat",
                json={"message": "hilo"},
                headers={"Authorization": "Bearer test-master-key"},
            )
    finally:
        app.dependency_overrides.pop(get_chat_service, None)

    assert response.status_code == 200
    assert threads["llm"] != threads["event_loop"]
