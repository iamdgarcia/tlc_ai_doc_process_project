from __future__ import annotations

import json
from typing import Any

from langsmith import traceable
from openai import OpenAI
from openai.types.chat import ChatCompletion, ChatCompletionToolParam
from sqlalchemy.orm import Session

from app.analytics_questions import SUGGESTED_QUESTIONS
from app.core.config import settings
from app.repositories.analytics import AnalyticsRepository
from app.repositories.sql_documents import SQLDocumentRepository
from app.services.llm import _get_wrapped_client

GET_TICKET_DATA_TOOL = ChatCompletionToolParam(
    type="function",
    function={
        "name": "get_ticket_data",
        "description": "Returns the data of a specific ticket from the database",
        "parameters": {
            "type": "object",
            "properties": {
                "ticket_id": {
                    "type": "string",
                    "description": "The ID of the ticket to retrieve",
                }
            },
            "required": ["ticket_id"],
        },
    },
)

GET_LIST_TICKETS_TOOL = ChatCompletionToolParam(
    type="function",
    function={
        "name": "get_list_tickets",
        "description": "Returns a list of tickets from the database",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "The maximum number of tickets to return",
                }
            },
            "required": ["limit"],
        },
    },
)


def _period_tool(name: str, description: str) -> ChatCompletionToolParam:
    return ChatCompletionToolParam(
        type="function",
        function={
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of days to analyse, ending on the latest stored ticket date",
                        "default": 365,
                    }
                },
            },
        },
    )


GET_PURCHASE_FREQUENCY_TOOL = _period_tool(
    "get_purchase_frequency",
    "Counts shopping visits/tickets and calculates purchase frequency for a period.",
)
GET_SPENDING_SUMMARY_TOOL = _period_tool(
    "get_spending_summary",
    "Returns total spend, average ticket and spend by supermarket for a period.",
)
GET_PRODUCT_QUANTITIES_TOOL = ChatCompletionToolParam(
    type="function",
    function={
        "name": "get_product_quantities",
        "description": "Returns total purchased quantity, purchase count and spend per product and unit.",
        "parameters": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "default": 365},
                "limit": {"type": "integer", "default": 20},
            },
        },
    },
)
COMPARE_PRODUCT_PRICES_TOOL = ChatCompletionToolParam(
    type="function",
    function={
        "name": "compare_product_prices",
        "description": "Returns the chronological price history and price difference for one product.",
        "parameters": {
            "type": "object",
            "properties": {
                "product_name": {"type": "string", "description": "Product name or part of it"},
                "days": {"type": "integer", "default": 3650},
            },
            "required": ["product_name"],
        },
    },
)
GET_FREQUENT_QUESTIONS_TOOL = ChatCompletionToolParam(
    type="function",
    function={
        "name": "get_frequent_questions",
        "description": "Returns examples of frequent questions supported by the ticket assistant.",
        "parameters": {"type": "object", "properties": {}},
    },
)

CHAT_TOOLS = [
    GET_TICKET_DATA_TOOL,
    GET_LIST_TICKETS_TOOL,
    GET_PURCHASE_FREQUENCY_TOOL,
    GET_SPENDING_SUMMARY_TOOL,
    GET_PRODUCT_QUANTITIES_TOOL,
    COMPARE_PRODUCT_PRICES_TOOL,
    GET_FREQUENT_QUESTIONS_TOOL,
]

SYSTEM_MESSAGE = {
    "role": "system",
    "content": (
        "Eres el asistente de compras de Luma Spend. Responde en español de forma breve y clara. "
        "Usa siempre las herramientas para contestar preguntas sobre tickets, frecuencia, gasto, "
        "cantidades o precios; nunca inventes datos. El periodo termina en la fecha del último ticket "
        "almacenado, no en la fecha actual. Aclara la unidad de las cantidades y no mezcles unidades "
        "distintas. Si faltan datos, dilo explícitamente."
    ),
}


def _trace_chat_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    """Exclude the service instance while retaining prompts in LangSmith."""

    return {"messages": inputs.get("messages", [])}


def _trace_chat_output(response: ChatCompletion) -> dict[str, Any]:
    """Expose standard token usage so LangSmith can calculate model cost."""

    output = response.model_dump(exclude_none=True)
    usage = output.pop("usage", None)
    if usage:
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        output["usage_metadata"] = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": usage.get("total_tokens", input_tokens + output_tokens),
        }
    return output


class ChatService:
    """Answer questions about stored tickets using LLM tool calls."""

    def __init__(
        self, session: Session | None = None, client: OpenAI | None = None
    ) -> None:
        self._repository = SQLDocumentRepository(session) if session else None
        self._analytics = AnalyticsRepository(session) if session else None
        # The dashboard and upload API must be able to start without opening an
        # LLM client. Initialise it only when the first chat message arrives.
        self._client = client
        self.messages: list[dict[str, Any]] = []

    def set_session(self, session: Session) -> None:
        """Set the SQLAlchemy session for the service."""
        self._repository = SQLDocumentRepository(session)
        self._analytics = AnalyticsRepository(session)

    def reset_conversation(self) -> None:
        """Reset the conversation history."""
        self.messages = []

    def chat(self, message: str) -> str:
        self.messages.append({"role": "user", "content": message})
        for _ in range(8):
            response = self._call_llm(self.messages)
            assistant_message = response.choices[0].message
            self.messages.append(assistant_message.model_dump(exclude_none=True))

            if not assistant_message.tool_calls:
                return assistant_message.content or ""

            for tool_call in assistant_message.tool_calls:
                result = self._handle_tool_call(
                    tool_call.function.name,
                    self._parse_tool_arguments(tool_call.function.arguments),
                )
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
        return "No he podido completar la consulta después de varios pasos. Prueba a reformularla."

    @traceable(
        name="Chat Completion",
        run_type="llm",
        metadata={
            "ls_provider": "novita",
            "ls_model_name": settings.openai_chat_model,
            "ls_model_type": "chat",
        },
        process_inputs=_trace_chat_inputs,
        process_outputs=_trace_chat_output,
    )
    def _call_llm(self, messages: list[dict[str, Any]]) -> ChatCompletion:
        if self._client is None:
            self._client = _get_wrapped_client()
        return self._client.chat.completions.create(
            model=settings.openai_chat_model,
            messages=[SYSTEM_MESSAGE, *messages],
            temperature=0.2,
            tools=CHAT_TOOLS,
        )

    @staticmethod
    def _parse_tool_arguments(arguments: str | dict[str, Any]) -> dict[str, Any]:
        if isinstance(arguments, dict):
            return arguments
        if not arguments.strip():
            return {}
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _handle_tool_call(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if self._repository is None or self._analytics is None:
            return {"error": "Database session is not configured"}
        if tool_name == "get_list_tickets":
            return self._repository.get_ticket_list(arguments.get("limit", 10))
        if tool_name == "get_ticket_data":
            return self._repository.get_ticket_data(arguments.get("ticket_id"))
        if tool_name == "get_purchase_frequency":
            return self._analytics.get_purchase_frequency(arguments.get("days", 365))
        if tool_name == "get_spending_summary":
            return self._analytics.get_spending_summary(arguments.get("days", 365))
        if tool_name == "get_product_quantities":
            return self._analytics.get_product_quantities(
                arguments.get("days", 365), arguments.get("limit", 20)
            )
        if tool_name == "compare_product_prices":
            return self._analytics.compare_product_prices(
                arguments.get("product_name", ""), arguments.get("days", 3650)
            )
        if tool_name == "get_frequent_questions":
            return SUGGESTED_QUESTIONS
        return {"error": f"Unknown tool: {tool_name}"}
