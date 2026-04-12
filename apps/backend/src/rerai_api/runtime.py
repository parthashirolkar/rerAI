from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4, uuid5

from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from langchain_core.messages import BaseMessage
from langchain_core.messages.base import message_to_dict
from langgraph.types import Command, Send, StateSnapshot

from .db import MetadataStore, RunRecord, ThreadRecord, utc_now

GRAPH_ID = "rerai"
SYSTEM_ASSISTANT_NAMESPACE = UUID("6ba7b821-9dad-11d1-80b4-00c04fd430c8")
SYSTEM_ASSISTANT_ID = str(uuid5(SYSTEM_ASSISTANT_NAMESPACE, GRAPH_ID))


def json_safe(value: Any) -> Any:
    if isinstance(value, BaseMessage):
        return message_to_dict(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, UUID):
        return str(value)
    if is_dataclass(value):
        return json_safe(asdict(value))
    if isinstance(value, dict):
        return {str(key): json_safe(next_value) for key, next_value in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    try:
        return jsonable_encoder(value)
    except Exception:
        return str(value)


def parse_stream_modes(value: Any) -> list[str]:
    if value is None:
        return ["values"]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return ["values"]
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                return [stripped]
            return [str(item) for item in parsed] or ["values"]
        return [stripped]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value] or ["values"]
    return ["values"]


def parse_assistant_id(assistant_id: str) -> str:
    if assistant_id in {GRAPH_ID, SYSTEM_ASSISTANT_ID}:
        return GRAPH_ID
    raise KeyError(f"Assistant '{assistant_id}' not found")


def assistant_payload() -> dict[str, Any]:
    now = utc_now().isoformat()
    return {
        "assistant_id": SYSTEM_ASSISTANT_ID,
        "graph_id": GRAPH_ID,
        "created_at": now,
        "updated_at": now,
        "metadata": {"created_by": "system"},
        "config": {},
        "context": {},
        "name": GRAPH_ID,
        "description": "rerAI permitting assistant",
    }


def _graph_schemas(graph) -> dict[str, Any]:
    try:
        input_schema = graph.get_input_jsonschema()
    except Exception:
        input_schema = None
    try:
        output_schema = graph.get_output_jsonschema()
    except Exception:
        output_schema = None
    try:
        state_schema = graph.get_output_jsonschema()
    except Exception:
        state_schema = None
    try:
        config_schema = graph.config_schema().model_json_schema()
    except Exception:
        config_schema = None
    try:
        context_schema = graph.get_context_jsonschema()
    except Exception:
        context_schema = None
    return {
        "graph_id": GRAPH_ID,
        "input_schema": input_schema,
        "output_schema": output_schema,
        "state_schema": state_schema,
        "config_schema": config_schema,
        "context_schema": context_schema,
    }


def checkpoint_from_config(config: dict[str, Any] | None) -> dict[str, Any] | None:
    if not config:
        return None
    configurable = config.get("configurable", {})
    checkpoint = {}
    for key in ("thread_id", "checkpoint_ns", "checkpoint_id", "checkpoint_map"):
        if key in configurable and configurable[key] is not None:
            checkpoint[key] = json_safe(configurable[key])
    return checkpoint or None


def format_state_snapshot(snapshot: StateSnapshot) -> dict[str, Any]:
    payload = {
        "values": json_safe(snapshot.values),
        "next": json_safe(list(snapshot.next)),
        "checkpoint": checkpoint_from_config(snapshot.config),
        "metadata": json_safe(snapshot.metadata),
        "created_at": snapshot.created_at,
        "parent_config": checkpoint_from_config(snapshot.parent_config),
        "tasks": json_safe(list(snapshot.tasks)),
        "interrupts": json_safe(list(snapshot.interrupts)),
    }
    return payload


def thread_payload(record: ThreadRecord) -> dict[str, Any]:
    return {
        "thread_id": record.thread_id,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "metadata": record.metadata,
        "status": record.status,
    }


def run_payload(record: RunRecord) -> dict[str, Any]:
    return {
        "run_id": record.run_id,
        "thread_id": record.thread_id,
        "assistant_id": record.assistant_id,
        "status": record.status,
        "metadata": record.metadata,
        "kwargs": {
            "config": record.config,
            "context": record.context,
            "input": record.input_payload,
            "command": record.command_payload,
            "stream_mode": record.stream_mode,
        },
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "multitask_strategy": None,
        "error": record.error,
    }


@dataclass(slots=True)
class PersistedEvent:
    stream_id: int
    event: str
    data: Any


@dataclass(slots=True)
class ActiveRun:
    run_id: str
    thread_id: str
    on_disconnect: str
    task: asyncio.Task[None]
    subscribers: set[asyncio.Queue[PersistedEvent | None]]


class RunManager:
    def __init__(self, store: MetadataStore, graph) -> None:
        self.store = store
        self.graph = graph
        self.active_runs: dict[str, ActiveRun] = {}
        self._lock = asyncio.Lock()

    async def start_run(
        self,
        *,
        thread_id: str,
        assistant_id: str,
        payload: dict[str, Any],
    ) -> RunRecord:
        stream_modes = parse_stream_modes(payload.get("stream_mode"))
        multitask_strategy = payload.get("multitask_strategy")
        active_for_thread = [
            active
            for active in self.active_runs.values()
            if active.thread_id == thread_id
        ]
        if active_for_thread:
            if multitask_strategy == "interrupt":
                for active in active_for_thread:
                    active.task.cancel()
            else:
                raise RuntimeError(f"Thread '{thread_id}' already has an active run")
        run_id = str(uuid4())
        run_record = await asyncio.to_thread(
            self.store.create_run,
            run_id=run_id,
            thread_id=thread_id,
            assistant_id=assistant_id,
            metadata=json_safe(payload.get("metadata") or {}),
            config=json_safe(payload.get("config")),
            context=json_safe(payload.get("context")),
            input_payload=json_safe(payload.get("input")),
            command_payload=json_safe(payload.get("command")),
            stream_mode=stream_modes,
            on_disconnect=payload.get("on_disconnect", "continue"),
        )
        async with self._lock:
            task = asyncio.create_task(
                self._run_graph(
                    run_id=run_id,
                    thread_id=thread_id,
                    assistant_id=assistant_id,
                    payload=payload,
                    stream_modes=stream_modes,
                )
            )
            self.active_runs[run_id] = ActiveRun(
                run_id=run_id,
                thread_id=thread_id,
                on_disconnect=payload.get("on_disconnect", "continue"),
                task=task,
                subscribers=set(),
            )
        return run_record

    async def stream_response(
        self,
        *,
        run_id: str,
        thread_id: str,
        last_event_id: int = 0,
        cancel_on_disconnect: bool = False,
    ) -> StreamingResponse:
        headers = {
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Location": f"/threads/{thread_id}/runs/{run_id}",
            "Location": f"/threads/{thread_id}/runs/{run_id}/stream",
        }

        async def body():
            replay = await asyncio.to_thread(
                self.store.list_run_events, run_id, after_id=last_event_id
            )
            last_seen = last_event_id
            for event in replay:
                last_seen = event.stream_id
                yield serialize_sse(event.stream_id, event.event, event.data)
                if event.event == "end":
                    return
            queue: asyncio.Queue[PersistedEvent | None] | None = None
            active = self.active_runs.get(run_id)
            if active is None:
                run_record = await asyncio.to_thread(
                    self.store.get_run, run_id, thread_id=thread_id
                )
                if run_record is not None and run_record.status != "running":
                    return
                return
            queue = asyncio.Queue()
            active.subscribers.add(queue)
            try:
                gap_events = await asyncio.to_thread(
                    self.store.list_run_events, run_id, after_id=last_seen
                )
                for event in gap_events:
                    last_seen = event.stream_id
                    yield serialize_sse(event.stream_id, event.event, event.data)
                    if event.event == "end":
                        return
                run_record = await asyncio.to_thread(
                    self.store.get_run, run_id, thread_id=thread_id
                )
                if run_record is not None and run_record.status != "running":
                    return
                while True:
                    item = await queue.get()
                    if item is None:
                        break
                    last_seen = item.stream_id
                    yield serialize_sse(item.stream_id, item.event, item.data)
                    if item.event == "end":
                        break
            except asyncio.CancelledError:
                if cancel_on_disconnect or active.on_disconnect == "cancel":
                    active.task.cancel()
                raise
            finally:
                if queue is not None:
                    active.subscribers.discard(queue)

        return StreamingResponse(
            body(), media_type="text/event-stream", headers=headers
        )

    async def _run_graph(
        self,
        *,
        run_id: str,
        thread_id: str,
        assistant_id: str,
        payload: dict[str, Any],
        stream_modes: list[str],
    ) -> None:
        interrupted = False
        await self._emit(run_id, thread_id, "metadata", {"run_id": run_id})
        config = build_runnable_config(thread_id=thread_id, payload=payload)
        input_value = build_graph_input(payload)
        try:
            async for chunk in self.graph.astream(
                input_value,
                config=config,
                context=payload.get("context"),
                stream_mode=stream_modes,
                interrupt_before=payload.get("interrupt_before"),
                interrupt_after=payload.get("interrupt_after"),
                durability=payload.get("durability"),
                subgraphs=bool(payload.get("stream_subgraphs", False)),
            ):
                event_name, data = normalize_stream_chunk(chunk)
                normalized = json_safe(data)
                if (
                    event_name == "values"
                    and isinstance(normalized, dict)
                    and normalized.get("__interrupt__")
                ):
                    interrupted = True
                await self._emit(run_id, thread_id, event_name, normalized)
            status = "interrupted" if interrupted else "completed"
            await asyncio.to_thread(
                self.store.finish_run, run_id=run_id, thread_id=thread_id, status=status
            )
        except asyncio.CancelledError:
            await asyncio.to_thread(
                self.store.finish_run,
                run_id=run_id,
                thread_id=thread_id,
                status="cancelled",
                error={"message": "Run cancelled"},
            )
            await self._emit(run_id, thread_id, "error", {"message": "Run cancelled"})
            raise
        except Exception as exc:
            await asyncio.to_thread(
                self.store.finish_run,
                run_id=run_id,
                thread_id=thread_id,
                status="error",
                error={"message": str(exc)},
            )
            await self._emit(run_id, thread_id, "error", {"message": str(exc)})
        finally:
            await self._emit(run_id, thread_id, "end", None)
            async with self._lock:
                active = self.active_runs.pop(run_id, None)
                if active is not None:
                    for queue in list(active.subscribers):
                        await queue.put(None)

    async def _emit(self, run_id: str, thread_id: str, event: str, data: Any) -> None:
        stream_id = await asyncio.to_thread(
            self.store.append_run_event,
            run_id=run_id,
            thread_id=thread_id,
            event=event,
            data=data,
        )
        active = self.active_runs.get(run_id)
        if active is None:
            return
        persisted = PersistedEvent(stream_id=stream_id, event=event, data=data)
        for queue in list(active.subscribers):
            await queue.put(persisted)


def serialize_sse(stream_id: int, event: str, data: Any) -> bytes:
    payload = json.dumps(json_safe(data), ensure_ascii=True, separators=(",", ":"))
    return f"id: {stream_id}\nevent: {event}\ndata: {payload}\n\n".encode("utf-8")


def normalize_stream_chunk(chunk: Any) -> tuple[str, Any]:
    if isinstance(chunk, tuple):
        if len(chunk) == 2:
            event, data = chunk
            return str(event), data
        if len(chunk) == 3:
            event, namespace, data = chunk
            if isinstance(namespace, (list, tuple)) and namespace:
                return f"{event}|{'|'.join(str(item) for item in namespace)}", data
            return str(event), data
    return "values", chunk


def build_command(payload: dict[str, Any] | None) -> Command | None:
    if not payload:
        return None
    goto = payload.get("goto")
    if isinstance(goto, dict) and goto.get("node"):
        goto_value = Send(str(goto["node"]), goto.get("input"))
    elif isinstance(goto, list):
        goto_value = [
            Send(str(item["node"]), item.get("input"))
            if isinstance(item, dict) and item.get("node")
            else item
            for item in goto
        ]
    else:
        goto_value = goto
    return Command(
        update=payload.get("update"), resume=payload.get("resume"), goto=goto_value
    )


def build_graph_input(payload: dict[str, Any]) -> Any:
    command = build_command(payload.get("command"))
    if command is not None:
        return command
    return payload.get("input")


def build_runnable_config(*, thread_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    config = json_safe(payload.get("config")) or {}
    configurable = dict(config.get("configurable") or {})
    configurable["thread_id"] = thread_id
    if payload.get("checkpoint_id"):
        configurable["checkpoint_id"] = payload["checkpoint_id"]
    if payload.get("checkpoint"):
        configurable.update(payload["checkpoint"])
    config["configurable"] = configurable
    return config


class BackendRuntime:
    def __init__(
        self,
        database_uri: str,
        *,
        graph=None,
        metadata_store: MetadataStore | None = None,
    ) -> None:
        self.database_uri = database_uri
        self.graph = graph
        self.metadata_store = metadata_store or MetadataStore(database_uri)
        self.run_manager: RunManager | None = (
            RunManager(self.metadata_store, self.graph) if self.graph is not None else None
        )

    async def setup(self) -> None:
        if self.graph is None:
            from rerai_agent.graph import build_graph

            self.graph = build_graph()
        if self.run_manager is None:
            self.run_manager = RunManager(self.metadata_store, self.graph)
        await asyncio.to_thread(self.metadata_store.setup)

    async def get_assistant(self, assistant_id: str) -> dict[str, Any]:
        parse_assistant_id(assistant_id)
        return assistant_payload()

    async def get_schemas(self, assistant_id: str) -> dict[str, Any]:
        parse_assistant_id(assistant_id)
        return _graph_schemas(self.graph)
