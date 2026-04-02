import os

from dotenv import load_dotenv
from langchain_ollama import OllamaEmbeddings
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

load_dotenv()

OPENROUTER_API_KEY = SecretStr(os.environ["OPENROUTER_API_KEY"])
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

CHAT_MODEL = "qwen/qwen3.6-plus:free"
SUBAGENT_MODEL = "nvidia/nemotron-3-nano-30b-a3b:free"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
EMBEDDING_MODEL = "embeddinggemma:latest"


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
    return OllamaEmbeddings(
        model=EMBEDDING_MODEL,
        base_url=OLLAMA_BASE_URL,
    )
