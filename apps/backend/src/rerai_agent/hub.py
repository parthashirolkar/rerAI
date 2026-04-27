from __future__ import annotations

import os
from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore
from pydantic import SecretStr

from rerai_agent.prompts import SYSTEM_PROMPT


_BASE_DIR = Path(__file__).resolve().parent
_DEFAULT_MEMORY_FILE = _BASE_DIR / "memory" / "AGENT_KNOWLEDGE.md"
_DEFAULT_SKILLS_DIR = _BASE_DIR / "skills"


def _default_memory_files() -> list[str | Path]:
    if _DEFAULT_MEMORY_FILE.exists():
        return [str(_DEFAULT_MEMORY_FILE)]
    return []


def _default_tools() -> list[Callable]:
    from rerai_agent.factories import default_registry

    return list(default_registry().assemble().tools)


def _default_subagents() -> list[Any]:
    from rerai_agent.factories import default_registry

    return list(default_registry().assemble().subagents)


@dataclass(frozen=True, slots=True)
class AgentHubConfig:
    database_uri: str | None = None
    openrouter_api_key: SecretStr | None = None
    chat_model: str = "nvidia/nemotron-3-super-120b-a12b:free"
    subagent_model: str = "nvidia/nemotron-3-nano-30b-a3b:free"
    embedding_model: str = "nvidia/llama-nemotron-embed-vl-1b-v2:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    memory_files: Sequence[str | Path] = field(default_factory=_default_memory_files)
    skills_dir: str | Path | None = field(
        default_factory=lambda: str(_DEFAULT_SKILLS_DIR)
    )
    system_prompt: str = SYSTEM_PROMPT
    tools: Sequence[Callable] = field(default_factory=_default_tools)
    subagents: Sequence[Any] = field(default_factory=_default_subagents)
    backend_factory: Callable[[Any], Any] | None = None
    interrupt_on: Sequence[str] | None = None
    setup_db: bool = True
    init_udcpr_store: bool = True

    @classmethod
    def from_env(
        cls, *, env_loader: Callable[[], None] | None = None
    ) -> AgentHubConfig:
        """Reads .env and os.environ. THE ONLY PLACE ENV IS TOUCHED."""
        if env_loader is not None:
            env_loader()
        else:
            from rerai_agent.env import load_project_env

            load_project_env()

        api_key = os.environ.get("OPENROUTER_API_KEY")
        database_uri = os.environ.get("DATABASE_URI")

        return cls(
            database_uri=database_uri or None,
            openrouter_api_key=SecretStr(api_key) if api_key else None,
        )

    @classmethod
    def for_testing(
        cls,
        *,
        database_uri: str = "sqlite://:memory:",
        skip_udcpr: bool = True,
    ) -> AgentHubConfig:
        """Sensible defaults for tests. No env read."""
        return cls(
            database_uri=database_uri,
            setup_db=True,
            init_udcpr_store=not skip_udcpr,
        )


class AgentHub(AbstractAsyncContextManager):
    graph: Any | None
    config: AgentHubConfig
    checkpointer: BaseCheckpointSaver | None
    store: BaseStore | None

    def __init__(
        self,
        config: AgentHubConfig,
        *,
        llm: BaseChatModel | None = None,
        embeddings: Embeddings | None = None,
        checkpointer: BaseCheckpointSaver | None = None,
        store: BaseStore | None = None,
        model_provider=None,
        persistence=None,
    ) -> None:
        self.config = config
        self._llm = llm
        self._embeddings = embeddings
        self._checkpointer = checkpointer
        self._store = store
        self._model_provider = model_provider
        self._persistence = persistence
        self._udcpr_initialized = False
        self.graph = None
        self.checkpointer = checkpointer
        self.store = store

    @classmethod
    async def production(
        cls,
        *,
        database_uri: str | None = None,
        config: AgentHubConfig | None = None,
        backend_factory: Callable[[Any], Any] | None = None,
        interrupt_on: Sequence[str] | None = None,
    ) -> AgentHub:
        """One-liner for production:
        1. Loads env (if config not provided).
        2. Builds real LLM/embeddings.
        3. Connects to Postgres/SQLite.
        4. Initializes UDCPR store.
        5. Returns a ready-to-run hub.
        """
        if config is None:
            config = AgentHubConfig.from_env()
        if database_uri is not None:
            from dataclasses import replace

            config = replace(config, database_uri=database_uri)
        if backend_factory is not None:
            from dataclasses import replace

            config = replace(config, backend_factory=backend_factory)
        if interrupt_on is not None:
            from dataclasses import replace

            config = replace(config, interrupt_on=interrupt_on)
        hub = cls.build(config=config)
        await hub.setup()
        return hub

    @classmethod
    async def testing(
        cls,
        *,
        database_uri: str = "sqlite://:memory:",
        fake_llm: BaseChatModel | None = None,
        fake_embeddings: Embeddings | None = None,
        skip_udcpr: bool = True,
        config: AgentHubConfig | None = None,
    ) -> AgentHub:
        """One-liner for tests:
        1. Uses in-memory SQLite (or no persistence if URI is empty).
        2. Injects fake LLM/embeddings when provided.
        3. Skips UDCPR by default.
        4. Fast setup / teardown.
        """
        if config is None:
            config = AgentHubConfig.for_testing(
                database_uri=database_uri,
                skip_udcpr=skip_udcpr,
            )
        hub = cls.build(
            config=config,
            llm=fake_llm,
            embeddings=fake_embeddings,
        )
        await hub.setup()
        return hub

    @classmethod
    def build(
        cls,
        *,
        config: AgentHubConfig,
        llm: BaseChatModel | None = None,
        embeddings: Embeddings | None = None,
        checkpointer: BaseCheckpointSaver | None = None,
        store: BaseStore | None = None,
    ) -> AgentHub:
        """Inject any dependency. Returns an UN-INITIALIZED hub.
        Caller MUST await hub.setup(). No env is read.
        """
        return cls(
            config=config,
            llm=llm,
            embeddings=embeddings,
            checkpointer=checkpointer,
            store=store,
        )

    def _get_model_provider(self):
        if self._model_provider is None:
            from rerai_agent.model_provider import OpenRouterModelProvider

            self._model_provider = OpenRouterModelProvider(
                api_key=self.config.openrouter_api_key,
                chat_model=self.config.chat_model,
                embedding_model=self.config.embedding_model,
                base_url=self.config.openrouter_base_url,
            )
        return self._model_provider

    def _build_llm(self) -> BaseChatModel:
        return self._get_model_provider().get_chat_model()

    def _build_embeddings(self) -> Embeddings:
        return self._get_model_provider().get_embeddings()

    def _get_persistence(self):
        if self._persistence is None:
            from rerai_agent.persistence import PersistenceAdapter

            self._persistence = PersistenceAdapter(
                database_uri=self.config.database_uri,
                setup_db=self.config.setup_db,
            )
        return self._persistence

    async def _resolve_persistence(
        self,
    ) -> tuple[BaseCheckpointSaver | None, BaseStore | None]:
        if self._checkpointer is not None or self._store is not None:
            return self._checkpointer, self._store
        checkpointer, store = await self._get_persistence().setup()
        self._checkpointer = checkpointer
        self._store = store
        self.checkpointer = checkpointer
        self.store = store
        return checkpointer, store

    async def setup(self) -> None:
        """Idempotent.
        - Resolves missing deps (LLM, checkpointer, store) from config.
        - Builds the deepagents graph.
        - Runs DB setup() if configured.
        - Initializes UDCPR store once per instance.
        """
        if self.graph is not None:
            return

        llm = self._llm
        if llm is None:
            llm = self._build_llm()

        if self.config.init_udcpr_store and not self._udcpr_initialized:
            from rerai_agent.tools.regulatory_tools import init_udcpr_store

            init_udcpr_store()
            self._udcpr_initialized = True

        checkpointer, store = await self._resolve_persistence()

        from deepagents import create_deep_agent
        from deepagents.backends import StateBackend

        self.graph = create_deep_agent(
            model=llm,
            tools=list(self.config.tools),
            subagents=list(self.config.subagents),
            memory=[str(f) for f in self.config.memory_files],
            skills=[str(self.config.skills_dir)] if self.config.skills_dir else [],
            system_prompt=self.config.system_prompt,
            checkpointer=checkpointer,
            store=store,
            backend=self.config.backend_factory
            or (lambda runtime: StateBackend(runtime)),
            interrupt_on=self.config.interrupt_on,
        )

    async def close(self) -> None:
        """Idempotent. Closes checkpointer, store, and any connection pools.
        NEVER calls asyncio.run(). Safe under pytest-asyncio and Uvicorn.
        """
        if self._persistence is not None:
            await self._persistence.close()
            self._persistence = None
        self._checkpointer = None
        self._store = None
        self.graph = None
        self.checkpointer = None
        self.store = None

    async def __aenter__(self) -> AgentHub:
        await self.setup()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.close()


# Re-export for tests that monkeypatch build_graph internals
from deepagents import create_deep_agent  # noqa: E402
from deepagents.backends import StateBackend  # noqa: E402


def build_graph(
    registry=None,
    checkpointer=None,
    store=None,
    backend=None,
    interrupt_on=None,
):
    """Standalone graph builder. Prefer AgentHub for lifecycle management."""
    from rerai_agent.factories import default_registry

    if registry is None:
        registry = default_registry()
    config = registry.assemble()
    return create_deep_agent(
        model=config.model,
        tools=config.tools,
        subagents=config.subagents,
        memory=[str(_DEFAULT_MEMORY_FILE)] if _DEFAULT_MEMORY_FILE.exists() else [],
        skills=[str(_DEFAULT_SKILLS_DIR)],
        system_prompt=SYSTEM_PROMPT,
        checkpointer=checkpointer,
        store=store,
        backend=backend or (lambda runtime: StateBackend(runtime)),
        interrupt_on=interrupt_on,
    )
