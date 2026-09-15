from __future__ import annotations

import json
from typing import Any

from langsmith import traceable
from openai import OpenAI
from openai.types.chat import ChatCompletion, ChatCompletionToolParam
from sqlalchemy.orm import Session

from app.core.config import settings
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
        self._client = _get_wrapped_client() if client is None else client
        self.messages: list[dict[str, Any]] = []

    def set_session(self, session: Session) -> None:
        """Set the SQLAlchemy session for the service."""
        self._repository = SQLDocumentRepository(session)

    def reset_conversation(self) -> None:
        """Reset the conversation history."""
        self.messages = []

    def chat(self, message: str) -> str:
        self.messages.append({"role": "user", "content": message})
        while True:
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
