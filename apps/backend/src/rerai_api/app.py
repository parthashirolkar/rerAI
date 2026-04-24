from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict

from rerai_agent.env import load_project_env

from .runtime import (
    BackendRuntime,
    GRAPH_ID,
    format_state_snapshot,
    parse_assistant_id,
    parse_stream_modes,
    thread_payload,
)


class ThreadCreateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    thread_id: str | None = None
    metadata: dict[str, Any] | None = None
    if_exists: Literal["raise", "do_nothing"] | None = None


class ThreadHistoryRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    limit: int = 10
    before: str | dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    checkpoint: dict[str, Any] | None = None


class StreamRunRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    assistant_id: str
    input: Any = None
    command: dict[str, Any] | None = None
    config: dict[str, Any] | None = None
    context: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    stream_mode: list[str] | str | None = None
    stream_subgraphs: bool = False
    stream_resumable: bool = False
    interrupt_before: list[str] | str | None = None
    interrupt_after: list[str] | str | None = None
    multitask_strategy: str | None = None
    if_not_exists: Literal["reject", "create"] | None = None
    on_disconnect: Literal["cancel", "continue"] = "continue"
    durability: str | None = None
    checkpoint: dict[str, Any] | None = None
    checkpoint_id: str | None = None
    webhook: str | None = None
    after_seconds: int | None = None


def _default_database_uri() -> str:
    return os.getenv("DATABASE_URI", "sqlite:///tmp/rerai-backend.db")


def _default_internal_secret() -> str:
    value = os.getenv("LANGGRAPH_INTERNAL_SHARED_SECRET", "").strip()
    return value


def _require_supported_features(payload: StreamRunRequest) -> None:
    unsupported = {}
    for key in ("webhook", "after_seconds"):
        value = getattr(payload, key)
        if value not in (None, False, [], {}):
            unsupported[key] = value
    if unsupported:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported fields for MVP1: {', '.join(sorted(unsupported))}",
        )


def _normalize_interrupts(value: list[str] | str | None) -> list[str] | str | None:
    if value is None:
        return None
    if isinstance(value, list):
        return value
    return [value]


def _parse_before_config(
    thread_id: str, before: str | dict[str, Any] | None
) -> dict[str, Any] | None:
    if before is None:
        return None
    configurable = {"thread_id": thread_id}
    if isinstance(before, str):
        configurable["checkpoint_id"] = before
    else:
        configurable.update(before)
    return {"configurable": configurable}


def _base_thread_config(
    thread_id: str, checkpoint: dict[str, Any] | None = None
) -> dict[str, Any]:
    configurable = {"thread_id": thread_id}
    if checkpoint:
        configurable.update(checkpoint)
    return {"configurable": configurable}


def _raise_if_missing_checkpointer(exc: Exception, *, detail: str) -> None:
    if isinstance(exc, ValueError) and str(exc) == "No checkpointer set":
        raise HTTPException(status_code=503, detail=detail) from exc


def _history_fallback_enabled(exc: Exception) -> bool:
    return isinstance(exc, NotImplementedError)


def get_runtime(request: Request) -> BackendRuntime:
    return request.app.state.runtime


def create_app(
    runtime: BackendRuntime | None = None,
    *,
    internal_secret: str | None = None,
) -> FastAPI:
    load_project_env()
    database_uri = (
        runtime.database_uri if runtime is not None else (_default_database_uri())
    )
    active_runtime = runtime or BackendRuntime(database_uri)
    shared_secret = internal_secret if internal_secret is not None else _default_internal_secret()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await active_runtime.setup()
        app.state.runtime = active_runtime
        yield

    app = FastAPI(title="rerAI Backend", version="0.1.0", lifespan=lifespan)

    @app.middleware("http")
    async def require_internal_secret(request: Request, call_next):
        if request.url.path == "/ok":
            return await call_next(request)

        if not shared_secret:
            return Response(
                status_code=500,
                content="Missing LANGGRAPH_INTERNAL_SHARED_SECRET",
            )

        provided = request.headers.get("x-rerai-internal-secret", "").strip()
        if provided != shared_secret:
            return Response(status_code=401, content="Unauthorized")
        return await call_next(request)

    @app.get("/ok")
    async def ok() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/info")
    async def info() -> dict[str, Any]:
        return {
            "version": "0.1.0",
            "flags": {
                "assistants": True,
                "crons": False,
                "langsmith": False,
                "langsmith_tracing_replicas": False,
            },
            "host": {
                "kind": "self-hosted",
                "project_id": None,
                "host_revision_id": None,
                "revision_id": None,
                "tenant_id": None,
            },
        }

    @app.get("/assistants/{assistant_id}")
    async def get_assistant(assistant_id: str, request: Request) -> dict[str, Any]:
        try:
            return await get_runtime(request).get_assistant(assistant_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/assistants/{assistant_id}/schemas")
    async def get_assistant_schemas(
        assistant_id: str, request: Request
    ) -> dict[str, Any]:
        try:
            return await get_runtime(request).get_schemas(assistant_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/threads")
    async def create_thread(
        payload: ThreadCreateRequest, request: Request, response: Response
    ) -> dict[str, Any]:
        thread_id = payload.thread_id or str(uuid4())
        try:
            record = await asyncio.to_thread(
                get_runtime(request).metadata_store.create_thread,
                thread_id,
                payload.metadata or {},
                if_exists=payload.if_exists or "raise",
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        response.headers["Content-Location"] = f"/threads/{record.thread_id}"
        return thread_payload(record)

    @app.get("/threads/{thread_id}")
    async def get_thread(thread_id: str, request: Request) -> dict[str, Any]:
        record = await asyncio.to_thread(
            get_runtime(request).metadata_store.get_thread, thread_id
        )
        if record is None:
            raise HTTPException(
                status_code=404, detail=f"Thread '{thread_id}' not found"
            )
        return thread_payload(record)

    @app.delete("/threads/{thread_id}", status_code=204)
    async def delete_thread(thread_id: str, request: Request) -> Response:
        deleted = await asyncio.to_thread(
            get_runtime(request).metadata_store.delete_thread, thread_id
        )
        if not deleted:
            raise HTTPException(
                status_code=404, detail=f"Thread '{thread_id}' not found"
            )
        return Response(status_code=204)

    @app.get("/threads/{thread_id}/state")
    async def get_thread_state(
        thread_id: str,
        request: Request,
        subgraphs: bool = Query(default=False),
    ) -> dict[str, Any]:
        thread_record = await asyncio.to_thread(
            get_runtime(request).metadata_store.get_thread, thread_id
        )
        if thread_record is None:
            raise HTTPException(
                status_code=404, detail=f"Thread '{thread_id}' not found"
            )
        try:
            snapshot = await get_runtime(request).graph.aget_state(
                _base_thread_config(thread_id),
                subgraphs=subgraphs,
            )
        except Exception as exc:
            _raise_if_missing_checkpointer(
                exc,
                detail="Thread state is unavailable because persistence is disabled",
            )
            raise
        return format_state_snapshot(snapshot)

    @app.post("/threads/{thread_id}/history")
    async def get_thread_history(
        thread_id: str, payload: ThreadHistoryRequest, request: Request
    ) -> list[dict[str, Any]]:
        thread_record = await asyncio.to_thread(
            get_runtime(request).metadata_store.get_thread, thread_id
        )
        if thread_record is None:
            raise HTTPException(
                status_code=404, detail=f"Thread '{thread_id}' not found"
            )
        try:
            history = get_runtime(request).graph.aget_state_history(
                _base_thread_config(thread_id, payload.checkpoint),
                filter=payload.metadata,
                before=_parse_before_config(thread_id, payload.before),
                limit=payload.limit,
            )
            snapshots = [format_state_snapshot(snapshot) async for snapshot in history]
        except Exception as exc:
            _raise_if_missing_checkpointer(
                exc,
                detail="Thread history is unavailable because persistence is disabled",
            )
            if _history_fallback_enabled(exc):
                try:
                    snapshot = await get_runtime(request).graph.aget_state(
                        _base_thread_config(thread_id, payload.checkpoint)
                    )
                except NotImplementedError:
                    return []
                return [format_state_snapshot(snapshot)]
            raise
        return snapshots

    @app.post("/runs/stream")
    async def stream_run_stateless(
        payload: StreamRunRequest, request: Request
    ) -> Response:
        _require_supported_features(payload)
        try:
            assistant_graph = parse_assistant_id(payload.assistant_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if assistant_graph != GRAPH_ID:
            raise HTTPException(
                status_code=404, detail=f"Assistant '{payload.assistant_id}' not found"
            )
        thread_record = await asyncio.to_thread(
            get_runtime(request).metadata_store.create_thread,
            str(uuid4()),
            payload.metadata or {},
            if_exists="raise",
        )
        return await _start_stream(thread_record.thread_id, payload, request)

    @app.post("/threads/{thread_id}/runs/stream")
    async def stream_thread_run(
        thread_id: str, payload: StreamRunRequest, request: Request
    ) -> Response:
        _require_supported_features(payload)
        try:
            parse_assistant_id(payload.assistant_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        store = get_runtime(request).metadata_store
        thread_record = await asyncio.to_thread(store.get_thread, thread_id)
        if thread_record is None:
            if payload.if_not_exists == "create":
                thread_record = await asyncio.to_thread(
                    store.create_thread,
                    thread_id,
                    payload.metadata or {},
                    if_exists="raise",
                )
            else:
                raise HTTPException(
                    status_code=404, detail=f"Thread '{thread_id}' not found"
                )
        return await _start_stream(thread_record.thread_id, payload, request)

    async def _start_stream(
        thread_id: str, payload: StreamRunRequest, request: Request
    ) -> Response:
        runtime = get_runtime(request)
        payload_dict = payload.model_dump()
        payload_dict["stream_mode"] = parse_stream_modes(
            payload_dict.get("stream_mode")
        )
        payload_dict["interrupt_before"] = _normalize_interrupts(
            payload_dict.get("interrupt_before")
        )
        payload_dict["interrupt_after"] = _normalize_interrupts(
            payload_dict.get("interrupt_after")
        )
        if payload_dict.get("multitask_strategy") not in (None, "interrupt"):
            raise HTTPException(
                status_code=422, detail="Unsupported multitask_strategy for MVP1"
            )
        try:
            run_record = await runtime.run_manager.start_run(
                thread_id=thread_id,
                assistant_id=payload.assistant_id,
                payload=payload_dict,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        response = await runtime.run_manager.stream_response(
            run_id=run_record.run_id, thread_id=thread_id
        )
        response.headers["Content-Location"] = (
            f"/threads/{thread_id}/runs/{run_record.run_id}"
        )
        response.headers["Location"] = (
            f"/threads/{thread_id}/runs/{run_record.run_id}/stream"
        )
        return response

    @app.get("/threads/{thread_id}/runs/{run_id}/stream")
    async def join_run_stream(
        thread_id: str,
        run_id: str,
        request: Request,
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
        stream_mode: str | None = Query(default=None),
        cancel_on_disconnect: bool = Query(default=False),
    ) -> Response:
        runtime = get_runtime(request)
        run_record = await asyncio.to_thread(
            runtime.metadata_store.get_run, run_id, thread_id=thread_id
        )
        if run_record is None:
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
        after_id = 0
        if last_event_id and last_event_id != "-1":
            try:
                after_id = int(last_event_id)
            except ValueError as exc:
                raise HTTPException(
                    status_code=422, detail="Invalid Last-Event-ID"
                ) from exc
        _ = parse_stream_modes(stream_mode) if stream_mode is not None else None
        return await runtime.run_manager.stream_response(
            run_id=run_id,
            thread_id=thread_id,
            last_event_id=after_id,
            cancel_on_disconnect=cancel_on_disconnect,
        )

    return app


app = create_app()
