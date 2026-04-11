import os

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pydantic import SecretStr

from rerai_agent.env import load_project_env

load_project_env()

os.environ.setdefault("USER_AGENT", "rerAI/0.1.0")

OPENROUTER_API_KEY = SecretStr(os.environ["OPENROUTER_API_KEY"])

MAHARERA_PUBLIC_USERNAME = os.environ.get(
    "MAHARERA_PUBLIC_USERNAME", "@maharera_public_view"
)
MAHARERA_PUBLIC_PASSWORD = os.environ.get("MAHARERA_PUBLIC_PASSWORD", "Maharera!@$1")
MAHARERA_CRYPTOJS_KEY = os.environ.get("MAHARERA_CRYPTOJS_KEY", "sdjhfsdkjgkls74385385")

CHAT_MODEL = "stepfun/step-3.5-flash:free"
SUBAGENT_MODEL = "nvidia/nemotron-3-nano-30b-a3b:free"
EMBEDDING_MODEL = "nvidia/llama-nemotron-embed-vl-1b-v2:free"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

CHROMA_TENANT = os.environ.get("CHROMA_TENANT", "c73d822b-82e7-4ba1-bd24-291c352b02f4")
CHROMA_DATABASE = os.environ.get("CHROMA_DATABASE", "RerAI-prod")


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


def get_chat_model(**kwargs):
    return ChatOpenAI(
        model=CHAT_MODEL,
        base_url=OPENROUTER_BASE_URL,
        api_key=OPENROUTER_API_KEY,
        **kwargs,
    )


def get_subagent_model(**kwargs):
    return ChatOpenAI(
        model=SUBAGENT_MODEL,
        base_url=OPENROUTER_BASE_URL,
        api_key=OPENROUTER_API_KEY,
        **kwargs,
    )


def get_embeddings():
    return OpenRouterEmbeddings(
        model=EMBEDDING_MODEL,
        base_url=OPENROUTER_BASE_URL,
        api_key=OPENROUTER_API_KEY,
        check_embedding_ctx_length=False,
    )
