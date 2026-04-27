from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from uuid import UUID, uuid5

from fastapi.responses import StreamingResponse

from rerai_agent.hub import AgentHub

from .adapters.langgraph import json_safe
from .orchestrator import RunOrchestrator, SseEvent
from .store import RunRecord, Store, ThreadRecord, utc_now

GRAPH_ID = "rerai"
SYSTEM_ASSISTANT_NAMESPACE = UUID("6ba7b821-9dad-11d1-80b4-00c04fd430c8")
SYSTEM_ASSISTANT_ID = str(uuid5(SYSTEM_ASSISTANT_NAMESPACE, GRAPH_ID))
logger = logging.getLogger(__name__)


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


def serialize_sse(stream_id: int, event: str, data: Any) -> bytes:
    payload = json.dumps(json_safe(data), ensure_ascii=True, separators=(",", ":"))
    return f"id: {stream_id}\nevent: {event}\ndata: {payload}\n\n".encode("utf-8")


def sse_response(
    events: Any, *, thread_id: str, run_id: str
) -> StreamingResponse:
    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Content-Location": f"/threads/{thread_id}/runs/{run_id}",
        "Location": f"/threads/{thread_id}/runs/{run_id}/stream",
    }

    async def body():
        async for event in events:
            if isinstance(event, SseEvent):
                yield serialize_sse(event.id, event.name, event.data)

    return StreamingResponse(body(), media_type="text/event-stream", headers=headers)


class BackendRuntime:
    def __init__(
        self,
        database_uri: str,
        *,
        graph=None,
        metadata_store: Store | None = None,
    ) -> None:
        self.database_uri = database_uri
        self.graph = graph
        self.metadata_store = metadata_store or Store(database_uri)
        self.orchestrator: RunOrchestrator | None = None
        self.hub = None

    async def setup(self) -> None:
        if self.graph is None:
            self.hub = await AgentHub.production(database_uri=self.database_uri)
            self.graph = self.hub.graph
        if self.orchestrator is None:
            from .adapters.db_event_store import DbEventStore
            from .adapters.langgraph import LangGraphAdapter
            from .ports import GraphPort

            graph_port = (
                self.graph
                if isinstance(self.graph, GraphPort)
                else LangGraphAdapter(self.graph)
            )
            event_store = DbEventStore(self.metadata_store)
            self.orchestrator = RunOrchestrator(
                graph=graph_port, store=event_store
            )
        await asyncio.to_thread(self.metadata_store.setup)

    async def get_assistant(self, assistant_id: str) -> dict[str, Any]:
        parse_assistant_id(assistant_id)
        return assistant_payload()

    async def get_schemas(self, assistant_id: str) -> dict[str, Any]:
        parse_assistant_id(assistant_id)
        return _graph_schemas(self.graph)
