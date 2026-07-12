"""Azure OpenAI implementation of LLMProvider (T-006).

Uses structured outputs (``response_format=<pydantic model>``) so extraction
is schema-validated by the API itself rather than by hand-parsing free-text
model output. Never touched by tests directly - they stub ``LLMProvider``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncAzureOpenAI

from app.core.config import Settings
from app.llm.provider import ChatMessage, LLMProvider, SchemaT
from app.observability.cost import report_usage


def _report(model: str, usage: Any) -> None:
    """Forward an Azure completion's usage to the T-030 cost sink, if any."""
    if usage is not None:
        report_usage(model, usage.prompt_tokens or 0, usage.completion_tokens or 0)


_API_VERSION = "2024-10-21"


class AzureOpenAIProvider(LLMProvider):
    def __init__(self, settings: Settings) -> None:
        self._client = AsyncAzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=_API_VERSION,
        )
        self._deployment = settings.azure_openai_chat_deployment

    async def extract(
        self, *, system_prompt: str, user_input: str, schema: type[SchemaT]
    ) -> SchemaT:
        completion = await self._client.chat.completions.parse(
            model=self._deployment,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ],
            response_format=schema,
        )
        _report(self._deployment, completion.usage)
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise ValueError("model produced no parseable structured output")
        return parsed

    async def chat(self, messages: list[ChatMessage]) -> str:
        completion = await self._client.chat.completions.create(
            model=self._deployment,
            messages=[dict(message) for message in messages],  # type: ignore[misc]
        )
        _report(self._deployment, completion.usage)
        content = completion.choices[0].message.content
        if content is None:
            raise ValueError("model produced no chat content")
        return content

    async def chat_stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        # stream_options widens the overload set past what mypy can match (a
        # dict literal isn't the SDK's typed param object) - the whole call
        # falls back to Any, so no per-argument ignore is needed below it.
        stream = await self._client.chat.completions.create(  # type: ignore[call-overload]
            model=self._deployment,
            messages=[dict(message) for message in messages],
            stream=True,
            stream_options={"include_usage": True},
        )
        async for chunk in stream:
            if getattr(chunk, "usage", None) is not None:
                _report(self._deployment, chunk.usage)
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta
