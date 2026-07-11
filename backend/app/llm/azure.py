"""Azure OpenAI implementation of LLMProvider (T-006).

Uses structured outputs (``response_format=<pydantic model>``) so extraction
is schema-validated by the API itself rather than by hand-parsing free-text
model output. Never touched by tests directly - they stub ``LLMProvider``.
"""

from __future__ import annotations

from openai import AsyncAzureOpenAI

from app.core.config import Settings
from app.llm.provider import ChatMessage, LLMProvider, SchemaT

_API_VERSION = "2024-10-21"


class AzureOpenAIProvider(LLMProvider):
    def __init__(self, settings: Settings) -> None:
        self._client = AsyncAzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=_API_VERSION,
        )
        self._deployment = settings.azure_openai_chat_deployment
        self._embed_deployment = settings.azure_openai_embed_deployment

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
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise ValueError("model produced no parseable structured output")
        return parsed

    async def chat(self, messages: list[ChatMessage]) -> str:
        completion = await self._client.chat.completions.create(
            model=self._deployment,
            messages=[dict(message) for message in messages],  # type: ignore[misc]
        )
        content = completion.choices[0].message.content
        if content is None:
            raise ValueError("model produced no chat content")
        return content

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self._client.embeddings.create(
            model=self._embed_deployment,
            input=texts,
        )
        return [item.embedding for item in response.data]
