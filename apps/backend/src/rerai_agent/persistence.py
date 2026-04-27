from __future__ import annotations

from contextlib import AsyncExitStack
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore


def _is_postgres_uri(value: str) -> bool:
    value = value.strip().lower()
    return value.startswith("postgresql://") or value.startswith("postgres://")


def _is_sqlite_uri(value: str) -> bool:
    return value.strip().lower().startswith("sqlite://")


def _sqlite_conn_string(value: str) -> str:
    return value[len("sqlite://") :]


class PersistenceAdapter:
    """Manages async checkpoint saver and store lifecycle."""

    def __init__(
        self,
        database_uri: str | None = None,
        *,
        setup_db: bool = True,
    ) -> None:
        self._database_uri = database_uri
        self._setup_db = setup_db
        self._exit_stack: AsyncExitStack | None = None
        self._checkpointer: BaseCheckpointSaver | None = None
        self._store: BaseStore | None = None

    async def setup(
        self,
    ) -> tuple[BaseCheckpointSaver | None, BaseStore | None]:
        if self._checkpointer is not None or self._store is not None:
            return self._checkpointer, self._store

        database_uri = self._database_uri
        if not database_uri:
            return None, None

        if not _is_sqlite_uri(database_uri) and not _is_postgres_uri(database_uri):
            return None, None

        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        from langgraph.store.postgres.aio import AsyncPostgresStore
        from langgraph.store.sqlite.aio import AsyncSqliteStore

        stack = AsyncExitStack()
        try:
            if _is_sqlite_uri(database_uri):
                conn_string = _sqlite_conn_string(database_uri)
                store = await stack.enter_async_context(
                    AsyncSqliteStore.from_conn_string(conn_string)
                )
                checkpointer = await stack.enter_async_context(
                    AsyncSqliteSaver.from_conn_string(conn_string)
                )
            elif _is_postgres_uri(database_uri):
                store = await stack.enter_async_context(
                    AsyncPostgresStore.from_conn_string(database_uri)
                )
                checkpointer = await stack.enter_async_context(
                    AsyncPostgresSaver.from_conn_string(database_uri)
                )
            else:
                await stack.aclose()
                return None, None

            if self._setup_db:
                await store.setup()
                await checkpointer.setup()

            self._exit_stack = stack
            self._checkpointer = checkpointer
            self._store = store
            return checkpointer, store
        except Exception:
            await stack.aclose()
            raise

    async def close(self) -> None:
        if self._exit_stack is not None:
            await self._exit_stack.aclose()
            self._exit_stack = None
        self._checkpointer = None
        self._store = None

    @property
    def checkpointer(self) -> BaseCheckpointSaver | None:
        return self._checkpointer

    @property
    def store(self) -> BaseStore | None:
        return self._store
