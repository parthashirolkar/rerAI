import os

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from rerai_agent.embeddings import OpenRouterEmbeddings

os.environ.setdefault("USER_AGENT", "rerAI/0.1.0")

OPENROUTER_API_KEY: SecretStr | None = None


def _get_openrouter_api_key() -> SecretStr:
    global OPENROUTER_API_KEY
    if OPENROUTER_API_KEY is None:
        OPENROUTER_API_KEY = SecretStr(os.environ["OPENROUTER_API_KEY"])
    return OPENROUTER_API_KEY


MAHARERA_PUBLIC_USERNAME = os.environ.get(
    "MAHARERA_PUBLIC_USERNAME", "@maharera_public_view"
)
MAHARERA_PUBLIC_PASSWORD = os.environ.get("MAHARERA_PUBLIC_PASSWORD", "Maharera!@$1")
MAHARERA_CRYPTOJS_KEY = os.environ.get("MAHARERA_CRYPTOJS_KEY", "sdjhfsdkjgkls74385385")

CHAT_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
SUBAGENT_MODEL = "nvidia/nemotron-3-nano-30b-a3b:free"
EMBEDDING_MODEL = "nvidia/llama-nemotron-embed-vl-1b-v2:free"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

CHROMA_TENANT = os.environ.get("CHROMA_TENANT", "c73d822b-82e7-4ba1-bd24-291c352b02f4")
CHROMA_DATABASE = os.environ.get("CHROMA_DATABASE", "RerAI-prod")


def get_chat_model(**kwargs):
    return ChatOpenAI(
        model=CHAT_MODEL,
        base_url=OPENROUTER_BASE_URL,
        api_key=_get_openrouter_api_key(),
        streaming=True,
        **kwargs,
    )


def get_subagent_model(**kwargs):
    return ChatOpenAI(
        model=SUBAGENT_MODEL,
        base_url=OPENROUTER_BASE_URL,
        api_key=_get_openrouter_api_key(),
        streaming=True,
        **kwargs,
    )


def get_embeddings():
    return OpenRouterEmbeddings(
        model=EMBEDDING_MODEL,
        base_url=OPENROUTER_BASE_URL,
        api_key=_get_openrouter_api_key(),
        check_embedding_ctx_length=False,
    )
