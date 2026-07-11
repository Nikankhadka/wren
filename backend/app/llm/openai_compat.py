"""Generic OpenAI-compatible implementation of LLMProvider.

One class covers every vendor that speaks the OpenAI wire format - OpenRouter,
Groq, Google's Gemini compatibility endpoint, Together, a local Ollama, and
OpenAI itself - selected purely by LLM_BASE_URL / LLM_API_KEY / LLM_MODEL, so
swapping hosted chat vendors is an env change, never a code change.

``extract`` relies on structured outputs (``response_format=<pydantic
model>`` json_schema), which the target endpoint/model must support - free
models that do include Gemini flash, DeepSeek, and Groq's llama-3.3-70b.
Never touched by tests directly - they stub ``LLMProvider``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from app.core.config import Settings
from app.llm.provider import ChatMessage, LLMProvider, SchemaT


class OpenAICompatProvider(LLMProvider):
    def __init__(self, settings: Settings) -> None:
        self._client = AsyncOpenAI(
            base_url=settings.llm_base_url,
            # Keyless endpoints (e.g. a local Ollama) ignore the value, but the
            # SDK requires one; hosted vendors reject a bad key server-side.
            api_key=settings.llm_api_key or "unused",
        )
        self._model = settings.llm_model

    async def extract(
        self, *, system_prompt: str, user_input: str, schema: type[SchemaT]
    ) -> SchemaT:
        completion = await self._client.chat.completions.parse(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ],
            response_format=schema,
        )
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise ValueError("model produced no parseable structured output")
        return parsed

    async def chat(self, messages: list[ChatMessage]) -> str:
        completion = await self._client.chat.completions.create(
            model=self._model,
            messages=[dict(message) for message in messages],  # type: ignore[misc]
        )
        content = completion.choices[0].message.content
        if content is None:
            raise ValueError("model produced no chat content")
        return content

    async def chat_stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=[dict(message) for message in messages],  # type: ignore[misc]
            stream=True,
        )
        # create()'s return type is a stream/non-stream union that mypy can't
        # narrow here (the messages kwarg's own type: ignore above already
        # widens the overload match) - stream=True always yields the async
        # iterable half of that union at runtime.
        async for chunk in stream:  # type: ignore[union-attr]
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta
