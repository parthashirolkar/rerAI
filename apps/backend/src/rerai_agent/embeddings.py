from __future__ import annotations

from langchain_openai import OpenAIEmbeddings


class OpenRouterEmbeddings(OpenAIEmbeddings):
    """OpenAIEmbeddings subclass that forces encoding_format='float' for OpenRouter compatibility."""

    def embed_documents(self, texts, chunk_size=None, **kwargs):
        kwargs.setdefault("encoding_format", "float")
        return super().embed_documents(texts, chunk_size=chunk_size, **kwargs)

    def embed_query(self, text, **kwargs):
        kwargs.setdefault("encoding_format", "float")
        return super().embed_query(text, **kwargs)

    async def aembed_documents(self, texts, chunk_size=None, **kwargs):
        kwargs.setdefault("encoding_format", "float")
        return await super().aembed_documents(texts, chunk_size=chunk_size, **kwargs)

    async def aembed_query(self, text, **kwargs):
        kwargs.setdefault("encoding_format", "float")
        return await super().aembed_query(text, **kwargs)
