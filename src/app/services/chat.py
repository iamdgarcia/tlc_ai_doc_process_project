from __future__ import annotations

import json
from typing import Any

from openai import OpenAI
from openai.types.chat import ChatCompletion, ChatCompletionToolParam
from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.sql_documents import SQLDocumentRepository


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


class ChatService:
    """Answer questions about stored tickets using LLM tool calls."""

    def __init__(self, session: Session, client: OpenAI | None = None) -> None:
        self._repository = SQLDocumentRepository(session)
        self._client = client or OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )

    def chat(self, message: str) -> str:
        messages: list[dict[str, Any]] = [{"role": "user", "content": message}]

        while True:
            response = self._call_llm(messages)
            assistant_message = response.choices[0].message
            messages.append(assistant_message.model_dump(exclude_none=True))

            if not assistant_message.tool_calls:
                return assistant_message.content or ""

            for tool_call in assistant_message.tool_calls:
                result = self._handle_tool_call(
                    tool_call.function.name,
                    self._parse_tool_arguments(tool_call.function.arguments),
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )

    def _call_llm(self, messages: list[dict[str, Any]]) -> ChatCompletion:
        return self._client.chat.completions.create(
            model=settings.openai_chat_model,
            messages=messages,
            temperature=0.2,
            tools=[GET_TICKET_DATA_TOOL, GET_LIST_TICKETS_TOOL],
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
        if tool_name == "get_list_tickets":
            return self._repository.get_ticket_list(arguments.get("limit", 10))
        if tool_name == "get_ticket_data":
            return self._repository.get_ticket_data(arguments.get("ticket_id"))
        return {"error": f"Unknown tool: {tool_name}"}
