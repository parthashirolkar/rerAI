from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator
from uuid import uuid4

from .ports import GraphPort, RunEventStorePort

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SseEvent:
    id: int
    name: str
    data: Any


@dataclass(slots=True)
class _ActiveRun:
    run_id: str
    thread_id: str
    on_disconnect: str
    task: asyncio.Task[None]
    subscribers: set[asyncio.Queue[SseEvent | None]]


class RunSubscription:
    """Handle for an active or completed run. Created only by ``RunOrchestrator``."""

    def __init__(
        self, run_id: str, thread_id: str, orchestrator: RunOrchestrator
    ) -> None:
        self.run_id = run_id
        self.thread_id = thread_id
        self._orchestrator = orchestrator

    async def events(
        self, *, last_event_id: int = 0, cancel_on_disconnect: bool = False
    ) -> AsyncIterator[SseEvent]:
        """Iterate replay → gap → live. Framework-agnostic."""
        store = self._orchestrator._store
        # Replay persisted events from the store.
        replay = await store.list_events(run_id=self.run_id, after_id=last_event_id)
        last_seen = last_event_id
        for event in replay:
            last_seen = event.stream_id
            yield SseEvent(id=event.stream_id, name=event.event, data=event.data)
            if event.event == "end":
                return

        # Determine whether the run is still active.
        queue: asyncio.Queue[SseEvent | None] | None = None
        active = self._orchestrator._active_runs.get(self.run_id)
        if active is None:
            # Run finished while replaying — catch any final events.
            final_events = await store.list_events(
                run_id=self.run_id, after_id=last_seen
            )
            for event in final_events:
                last_seen = event.stream_id
                yield SseEvent(id=event.stream_id, name=event.event, data=event.data)
                if event.event == "end":
                    return
            run_record = await store.get_run(
                run_id=self.run_id, thread_id=self.thread_id
            )
            if run_record is not None and run_record.status != "running":
                return
            return

        # Subscribe to the live queue and catch the gap.
        queue = asyncio.Queue()
        active.subscribers.add(queue)
        try:
            gap_events = await store.list_events(run_id=self.run_id, after_id=last_seen)
            for event in gap_events:
                last_seen = event.stream_id
                yield SseEvent(id=event.stream_id, name=event.event, data=event.data)
                if event.event == "end":
                    return
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
                if item.name == "end":
                    break
        except asyncio.CancelledError:
            if cancel_on_disconnect or active.on_disconnect == "cancel":
                active.task.cancel()
            raise
        finally:
            if queue is not None:
                active.subscribers.discard(queue)


class RunOrchestrator:
    def __init__(self, graph: GraphPort, store: RunEventStorePort) -> None:
        self._graph = graph
        self._store = store
        self._active_runs: dict[str, _ActiveRun] = {}
        self._lock = asyncio.Lock()

    async def start(
        self, *, thread_id: str, assistant_id: str, payload: dict[str, Any]
    ) -> RunSubscription:
        stream_modes = payload.get("stream_mode", ["values"])
        multitask_strategy = payload.get("multitask_strategy")
        active_for_thread = [
            active
            for active in self._active_runs.values()
            if active.thread_id == thread_id
        ]
        if active_for_thread:
            if multitask_strategy == "interrupt":
                for active in active_for_thread:
                    active.task.cancel()
            else:
                raise RuntimeError(f"Thread '{thread_id}' already has an active run")

        run_id = str(uuid4())
        run_record = await self._store.create_run(
            thread_id=thread_id,
            assistant_id=assistant_id,
            metadata=payload.get("metadata") or {},
            config=payload.get("config"),
            context=payload.get("context"),
            input_payload=payload.get("input"),
            command_payload=payload.get("command"),
            stream_mode=stream_modes,
            on_disconnect=payload.get("on_disconnect", "continue"),
            run_id=run_id,
        )
        run_id = run_record.run_id

        async with self._lock:
            task = asyncio.create_task(
                self._run_graph(
                    run_id=run_id,
                    thread_id=thread_id,
                    assistant_id=assistant_id,
                    payload=payload,
                )
            )
            self._active_runs[run_id] = _ActiveRun(
                run_id=run_id,
                thread_id=thread_id,
                on_disconnect=payload.get("on_disconnect", "continue"),
                task=task,
                subscribers=set(),
            )
        return RunSubscription(run_id=run_id, thread_id=thread_id, orchestrator=self)

    async def attach(self, *, run_id: str, thread_id: str) -> RunSubscription:
        return RunSubscription(run_id=run_id, thread_id=thread_id, orchestrator=self)

    async def state(
        self, *, thread_id: str, checkpoint: dict | None = None, subgraphs: bool = False
    ) -> dict[str, Any]:
        return await self._graph.get_state(
            thread_id=thread_id, checkpoint=checkpoint, subgraphs=subgraphs
        )

    async def history(
        self,
        *,
        thread_id: str,
        checkpoint: dict | None = None,
        limit: int = 10,
        before: dict | str | None = None,
        metadata_filter: dict | None = None,
    ) -> list[dict[str, Any]]:
        return await self._graph.get_history(
            thread_id=thread_id,
            checkpoint=checkpoint,
            limit=limit,
            before=before,
            metadata_filter=metadata_filter,
        )

    async def _run_graph(
        self, *, run_id: str, thread_id: str, assistant_id: str, payload: dict[str, Any]
    ) -> None:
        await self._emit(run_id, thread_id, "metadata", {"run_id": run_id})
        try:
            async for event_name, data in self._graph.stream(
                thread_id=thread_id,
                assistant_id=assistant_id,
                payload=payload,
            ):
                await self._emit(run_id, thread_id, event_name, data)
            status = "completed"
            await self._store.finish_run(
                run_id=run_id, thread_id=thread_id, status=status
            )
        except asyncio.CancelledError:
            await self._store.finish_run(
                run_id=run_id,
                thread_id=thread_id,
                status="cancelled",
                error={"message": "Run cancelled"},
            )
            await self._emit(run_id, thread_id, "error", {"message": "Run cancelled"})
            raise
        except Exception as exc:
            message = str(exc).strip()
            if not message:
                message = f"{type(exc).__name__}: {exc!r}"
            logger.exception(
                "Run failed",
                extra={
                    "run_id": run_id,
                    "thread_id": thread_id,
                    "assistant_id": assistant_id,
                },
            )
            await self._store.finish_run(
                run_id=run_id,
                thread_id=thread_id,
                status="error",
                error={"message": message},
            )
            await self._emit(run_id, thread_id, "error", {"message": message})
        finally:
            await self._emit(run_id, thread_id, "end", None)
            async with self._lock:
                active = self._active_runs.pop(run_id, None)
                if active is not None:
                    for queue in list(active.subscribers):
                        await queue.put(None)

    async def _emit(self, run_id: str, thread_id: str, event: str, data: Any) -> None:
        stream_id = await self._store.append_event(
            run_id=run_id,
            thread_id=thread_id,
            event=event,
            data=data,
        )
        active = self._active_runs.get(run_id)
        if active is None:
            return
        sse_event = SseEvent(id=stream_id, name=event, data=data)
        for queue in list(active.subscribers):
            await queue.put(sse_event)
