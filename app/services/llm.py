import logging
from typing import TypeVar

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


def _to_lc_messages(messages: list[dict]) -> list:
    """Convert raw dicts to LangChain message objects."""
    result = []
    for m in messages:
        role = m["role"]
        if role == "system":
            result.append(SystemMessage(content=m["content"]))
        elif role == "user":
            result.append(HumanMessage(content=m["content"]))
        elif role == "assistant":
            msg = AIMessage(content=m.get("content", ""))
            if m.get("tool_calls"):
                msg.tool_calls = m["tool_calls"]
            result.append(msg)
        elif role == "tool":
            result.append(
                ToolMessage(
                    content=m["content"],
                    tool_call_id=m["tool_call_id"],
                )
            )
    return result


def _log_usage(model: str | None, response) -> None:
    meta = getattr(response, "response_metadata", {})
    usage = meta.get("token_usage", {})
    logger.info(
        "LLM call — model=%s prompt_tokens=%s completion_tokens=%s",
        model or settings.openai_model,
        usage.get("prompt_tokens", "n/a"),
        usage.get("completion_tokens", "n/a"),
    )


def _ai_message_to_dict(msg: AIMessage) -> dict:
    """Convert an AIMessage to a serializable dict for state storage."""
    d: dict = {"role": "assistant", "content": msg.content}
    if msg.tool_calls:
        d["tool_calls"] = msg.tool_calls
    return d


async def chat_completion(
    messages: list[dict],
    tools: list[dict] | None = None,
    model: str | None = None,
    temperature: float = 0.3,
) -> dict:
    """Call LLM with optional tool definitions, returning a dict message.

    The returned dict has ``role``, ``content``, and optionally ``tool_calls``.
    """
    chat = ChatOpenAI(
        model=model or settings.openai_model,
        temperature=temperature,
        api_key=settings.openai_api_key,
    )
    if tools:
        chat = chat.bind_tools(tools)
    lc_msgs = _to_lc_messages(messages)
    result = await chat.ainvoke(lc_msgs)
    _log_usage(model, result)
    return _ai_message_to_dict(result)


async def structured_output(
    messages: list[dict],
    response_model: type[T],
    model: str | None = None,
    temperature: float = 0.3,
) -> T:
    """Call LLM with structured output, returning a typed Pydantic model."""
    llm = ChatOpenAI(
        model=model or settings.openai_model,
        temperature=temperature,
        api_key=settings.openai_api_key,
    ).with_structured_output(response_model, include_raw=True, )
    lc_msgs = _to_lc_messages(messages)
    result = await llm.ainvoke(lc_msgs)
    _log_usage(model, result["raw"])
    return result["parsed"]
