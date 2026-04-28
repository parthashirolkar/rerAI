from __future__ import annotations

from typing import Any, AsyncIterator, Protocol, runtime_checkable


@runtime_checkable
class GraphPort(Protocol):
    """Framework-agnostic graph execution."""

    async def stream(
        self, *, thread_id: str, assistant_id: str, payload: dict[str, Any]
    ) -> AsyncIterator[tuple[str, Any]]: ...

    async def get_state(
        self,
        *,
        thread_id: str,
        checkpoint: dict[str, Any] | None = None,
        subgraphs: bool = False,
    ) -> dict[str, Any]: ...

    async def get_history(
        self,
        *,
        thread_id: str,
        checkpoint: dict[str, Any] | None = None,
        limit: int = 10,
        before: dict[str, Any] | str | None = None,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]: ...


@runtime_checkable
class RunEventStorePort(Protocol):
    """Run and event persistence."""

    async def create_run(self, **kwargs: Any) -> Any: ...

    async def finish_run(
        self, *, run_id: str, thread_id: str, status: str, error: dict | None = None
    ) -> None: ...

    async def append_event(
        self, *, run_id: str, thread_id: str, event: str, data: Any
    ) -> int: ...

    async def list_events(self, *, run_id: str, after_id: int = 0) -> list[Any]: ...

    async def get_run(self, *, run_id: str, thread_id: str) -> Any | None: ...
