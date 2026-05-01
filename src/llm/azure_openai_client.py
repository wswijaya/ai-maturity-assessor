"""
Azure OpenAI client — thin subclass of OpenAICompatibleClient that swaps
the underlying SDK client for AzureOpenAI.

All completion and error-handling logic is inherited unchanged. Only
initialisation differs: Azure requires an endpoint URL and an api_version
instead of a generic base_url.
"""

from __future__ import annotations

from openai import AzureOpenAI

from src.llm.openai_compatible_client import OpenAICompatibleClient

DEFAULT_API_VERSION = "2024-02-01"


class AzureOpenAIClient(OpenAICompatibleClient):

    def __init__(
        self,
        model: str,
        azure_endpoint: str,
        api_key: str,
        api_version: str = DEFAULT_API_VERSION,
    ) -> None:
        self._model = model
        self._client = AzureOpenAI(
            azure_endpoint=azure_endpoint,
            api_key=api_key,
            api_version=api_version,
        )
