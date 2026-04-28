from __future__ import annotations

from typing import Any

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from pydantic import SecretStr


class OpenRouterModelProvider:
    """Builds LLM and embeddings instances from an OpenRouter config."""

    def __init__(
        self,
        *,
        api_key: SecretStr | None = None,
        chat_model: str = "nvidia/nemotron-3-super-120b-a12b:free",
        embedding_model: str = "nvidia/llama-nemotron-embed-vl-1b-v2:free",
        base_url: str = "https://openrouter.ai/api/v1",
    ) -> None:
        self._api_key = api_key
        self._chat_model = chat_model
        self._embedding_model = embedding_model
        self._base_url = base_url

    def get_chat_model(self, **kwargs: Any) -> BaseChatModel:
        from langchain_openai import ChatOpenAI

        if self._api_key is None:
            raise RuntimeError("No OpenRouter API key configured")
        return ChatOpenAI(
            model=self._chat_model,
            base_url=self._base_url,
            api_key=self._api_key,
            streaming=True,
            **kwargs,
        )

    def get_embeddings(self, **kwargs: Any) -> Embeddings:
        from rerai_agent.embeddings import OpenRouterEmbeddings

        if self._api_key is None:
            raise RuntimeError("No OpenRouter API key configured")
        return OpenRouterEmbeddings(
            model=self._embedding_model,
            base_url=self._base_url,
            api_key=self._api_key,
            check_embedding_ctx_length=False,
            **kwargs,
        )
