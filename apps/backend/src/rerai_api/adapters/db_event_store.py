from __future__ import annotations

import asyncio
from typing import Any

from rerai_api.ports import RunEventStorePort


class DbEventStore(RunEventStorePort):
    """Adapts the synchronous ``Store`` to the async ``RunEventStorePort`` protocol."""

    def __init__(self, store) -> None:
        self._store = store

    async def create_run(self, **kwargs: Any) -> Any:
        return await asyncio.to_thread(self._store.create_run, **kwargs)

    async def finish_run(
        self, *, run_id: str, thread_id: str, status: str, error: dict | None = None
    ) -> None:
        await asyncio.to_thread(
            self._store.finish_run, run_id, status=status, error=error
        )

    async def append_event(
        self, *, run_id: str, thread_id: str, event: str, data: Any
    ) -> int:
        return await asyncio.to_thread(
            self._store.append_event, run_id, event, data, thread_id=thread_id
        )

    async def list_events(self, *, run_id: str, after_id: int = 0) -> list[Any]:
        return await asyncio.to_thread(
            self._store.list_events, run_id, after=after_id
        )

    async def get_run(self, *, run_id: str, thread_id: str) -> Any | None:
        return await asyncio.to_thread(self._store.get_run, run_id)
