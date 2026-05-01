"""
OpenAI-compatible client — works with OpenAI, Ollama, LM Studio, and any
other server that implements the OpenAI chat completions API.

System prompt handling: OpenAI-compatible APIs carry the system prompt as
a message with role="system" prepended to the conversation, unlike Anthropic
which takes it as a separate parameter.

Structured output: tries response_format=json_schema (supported by OpenAI
and newer Ollama models); falls back to the base-class prompt-injection path
for models that don't support it.
"""

from __future__ import annotations

import json
from typing import Type

from openai import OpenAI
from pydantic import BaseModel

from src.llm.base import LLMClient


class OpenAICompatibleClient(LLMClient):

    def __init__(
        self,
        model: str,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self._model = model
        # OpenAI SDK requires a non-empty api_key even for local servers.
        self._client = OpenAI(
            base_url=base_url,
            api_key=api_key or "no-key-required",
        )

    def complete(
        self,
        messages: list[dict],
        system: str,
        max_tokens: int = 1024,
    ) -> str:
        full_messages = [{"role": "system", "content": system}, *messages]
        response = self._client.chat.completions.create(
            model=self._model,
            messages=full_messages,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content

    def complete_structured(
        self,
        messages: list[dict],
        system: str,
        response_model: Type[BaseModel],
        max_tokens: int = 4096,
    ) -> BaseModel:
        """Try json_schema response_format; fall back to prompt-based JSON."""
        try:
            full_messages = [{"role": "system", "content": system}, *messages]
            response = self._client.chat.completions.create(
                model=self._model,
                messages=full_messages,
                max_tokens=max_tokens,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": response_model.__name__,
                        "schema": response_model.model_json_schema(),
                        "strict": False,
                    },
                },
            )
            data = json.loads(response.choices[0].message.content)
            return response_model.model_validate(data)
        except Exception:
            return super().complete_structured(messages, system, response_model, max_tokens)
