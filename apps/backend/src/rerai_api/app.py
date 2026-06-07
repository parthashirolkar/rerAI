from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Literal
from uuid import UUID, uuid4, uuid5

from fastapi import FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .auth import AuthContext, authenticate_request, require_thread_owner
from .convex import ConvexAuthClient, ConvexHttpClient
from .finalization import (
    canonical_assistant_messages,
    reconcile_assistant_messages,
    streamed_assistant_messages,
)
from .runtime import (
    BackendRuntime,
    GRAPH_ID,
    parse_assistant_id,
    sse_response,
    thread_payload,
)

logger = logging.getLogger(__name__)


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


class TurnSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    turn_id: str = Field(alias="turnId", min_length=1)
    human_message_id: str = Field(alias="humanMessageId", min_length=1)
    ui_thread_id: str = Field(alias="uiThreadId", min_length=1)
    content: str = Field(min_length=1)


TURN_THREAD_NAMESPACE = UUID("8cbd6f64-6c75-4d27-b9dc-aad995ea6bba")
TURN_RUN_NAMESPACE = UUID("3d778561-9eb2-44d7-b42f-1cc9fc11a809")


def _stable_uuid(namespace: UUID, value: str) -> str:
    return str(uuid5(namespace, value))


def _default_database_uri() -> str:
    return os.getenv("DATABASE_URI", "sqlite:///tmp/rerai-backend.db")


def _default_client_origins() -> list[str]:
    configured = os.getenv("CLIENT_ORIGINS", "").strip()
    if not configured:
        return ["*"]
    return [origin.strip() for origin in configured.split(",") if origin.strip()]


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


def _raise_if_missing_checkpointer(exc: Exception, *, detail: str) -> None:
    if isinstance(exc, ValueError) and str(exc) == "No checkpointer set":
        raise HTTPException(status_code=503, detail=detail) from exc


def _history_fallback_enabled(exc: Exception) -> bool:
    return isinstance(exc, NotImplementedError)


def get_runtime(request: Request) -> BackendRuntime:
    return request.app.state.runtime


def get_auth(request: Request) -> AuthContext:
    auth = getattr(request.state, "auth", None)
    if not isinstance(auth, AuthContext):
        raise HTTPException(status_code=401, detail="Missing authorization token")
    return auth


async def authorize_thread(request: Request, thread_id: str) -> None:
    auth = get_auth(request)
    runtime = get_runtime(request)
    thread_record = await asyncio.to_thread(
        runtime.metadata_store.get_thread, thread_id
    )
    if thread_record is None:
        return
    if thread_record.metadata.get("convex_user_id") == auth.user.user_id:
        return
    await require_thread_owner(auth, request.app.state.convex_client, thread_id)


def user_scoped_metadata(
    auth: AuthContext, metadata: dict[str, Any] | None
) -> dict[str, Any]:
    next_metadata = dict(metadata or {})
    next_metadata.setdefault("convex_user_id", auth.user.user_id)
    return next_metadata


def create_app(
    runtime: BackendRuntime | None = None,
    *,
    convex_client: ConvexAuthClient | None = None,
) -> FastAPI:
    database_uri = (
        runtime.database_uri if runtime is not None else (_default_database_uri())
    )
    active_runtime = runtime or BackendRuntime(database_uri)
    active_convex_client = convex_client or ConvexHttpClient()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await active_runtime.setup()
        app.state.runtime = active_runtime
        app.state.convex_client = active_convex_client

        async def deliver_finalization(payload: dict[str, Any]) -> None:
            outbox_id = str(payload["finalizationId"])
            try:
                await active_convex_client.finalize_turn(payload)
            except Exception as exc:
                await asyncio.to_thread(
                    active_runtime.metadata_store.mark_outbox_failed,
                    outbox_id,
                    str(exc),
                )
                raise
            await asyncio.to_thread(
                active_runtime.metadata_store.mark_outbox_delivered,
                outbox_id,
            )

        async def finalize_run(
            run_id: str,
            thread_id: str,
            status: str,
            error: dict[str, Any] | None,
        ) -> None:
            run = await asyncio.to_thread(
                active_runtime.metadata_store.get_run, run_id
            )
            if run is None:
                return
            turn_id = run.metadata.get("turn_id")
            human_message_id = run.metadata.get("human_message_id")
            if not isinstance(turn_id, str) or not isinstance(
                human_message_id, str
            ):
                return
            try:
                state = await active_runtime.orchestrator.state(thread_id=thread_id)
            except Exception:
                logger.exception(
                    "Unable to read canonical state during turn finalization",
                    extra={"run_id": run_id, "thread_id": thread_id},
                )
                state = {"values": {"messages": []}}
            terminal_status = {
                "completed": "completed",
                "cancelled": "cancelled",
                "error": "failed",
            }.get(status, "failed")
            canonical_messages = canonical_assistant_messages(
                state, human_message_id=human_message_id
            )
            events = await asyncio.to_thread(
                active_runtime.metadata_store.list_events, run_id
            )
            payload: dict[str, Any] = {
                "finalizationId": run_id,
                "turnId": turn_id,
                "status": terminal_status,
                "assistantMessages": reconcile_assistant_messages(
                    canonical_messages,
                    streamed_assistant_messages(events),
                    preserve_display_only=terminal_status
                    in {"failed", "cancelled"},
                ),
            }
            if error and isinstance(error.get("message"), str):
                payload["errorMessage"] = error["message"]
            await asyncio.to_thread(
                active_runtime.metadata_store.enqueue_outbox,
                run_id,
                payload,
            )
            await deliver_finalization(payload)

        active_runtime.orchestrator.set_terminal_callback(finalize_run)
        orphaned_runs = await asyncio.to_thread(
            active_runtime.metadata_store.list_running_runs
        )
        for run in orphaned_runs:
            error = {"message": "Backend restarted before the run completed"}
            await asyncio.to_thread(
                active_runtime.metadata_store.finish_run,
                run.run_id,
                status="error",
                error=error,
            )
            await finalize_run(run.run_id, run.thread_id, "error", error)

        pending = await asyncio.to_thread(
            active_runtime.metadata_store.list_pending_outbox
        )
        for item in pending:
            try:
                await deliver_finalization(item["payload"])
            except Exception:
                logger.exception(
                    "Unable to replay turn finalization",
                    extra={"outbox_id": item["outbox_id"]},
                )

        async def replay_outbox() -> None:
            while True:
                await asyncio.sleep(5)
                items = await asyncio.to_thread(
                    active_runtime.metadata_store.list_pending_outbox
                )
                for item in items:
                    try:
                        await deliver_finalization(item["payload"])
                    except Exception:
                        logger.exception(
                            "Unable to retry turn finalization",
                            extra={"outbox_id": item["outbox_id"]},
                        )

        replay_task = asyncio.create_task(replay_outbox())
        try:
            yield
        finally:
            replay_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await replay_task

    app = FastAPI(title="rerAI Backend", version="0.1.0", lifespan=lifespan)

    @app.middleware("http")
    async def require_user_auth(request: Request, call_next):
        if request.url.path == "/ok" or request.method == "OPTIONS":
            return await call_next(request)

        try:
            request.state.auth = await authenticate_request(
                request.headers.get("authorization"),
                active_convex_client,
            )
        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code, content={"detail": exc.detail}
            )
        return await call_next(request)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_default_client_origins(),
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Last-Event-ID"],
        expose_headers=["Content-Location", "Location"],
    )

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

    @app.post("/chat/turns")
    async def submit_turn(
        payload: TurnSubmitRequest, request: Request
    ) -> dict[str, str]:
        auth = get_auth(request)
        content = payload.content.strip()
        if not content:
            raise HTTPException(status_code=422, detail="Content cannot be empty")

        try:
            turn = await request.app.state.convex_client.ensure_turn(
                auth.token,
                ui_thread_id=payload.ui_thread_id,
                turn_id=payload.turn_id,
                human_message_id=payload.human_message_id,
                content=content,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail="Unable to persist Conversation Turn"
            ) from exc
        if (
            turn.get("uiThreadId") != payload.ui_thread_id
            or turn.get("humanMessageId") != payload.human_message_id
            or turn.get("content") != content
        ):
            raise HTTPException(
                status_code=409,
                detail=f"Conversation Turn '{payload.turn_id}' already exists with different input",
            )

        runtime = get_runtime(request)
        thread_id = _stable_uuid(TURN_THREAD_NAMESPACE, payload.ui_thread_id)
        run_id = _stable_uuid(TURN_RUN_NAMESPACE, payload.turn_id)
        await asyncio.to_thread(
            runtime.metadata_store.create_thread,
            thread_id,
            metadata=user_scoped_metadata(
                auth,
                {
                    "ui_thread_id": payload.ui_thread_id,
                },
            ),
            if_exists="do_nothing",
        )
        try:
            await request.app.state.convex_client.mark_turn_running(
                auth.token,
                turn_id=payload.turn_id,
                langgraph_thread_id=thread_id,
                langgraph_run_id=run_id,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail="Unable to start Conversation Turn"
            ) from exc
        subscription = await runtime.orchestrator.start(
            thread_id=thread_id,
            assistant_id=GRAPH_ID,
            run_id=run_id,
            payload={
                "input": {
                    "messages": [
                        {
                            "type": "human",
                            "id": payload.human_message_id,
                            "content": content,
                        }
                    ]
                },
                "metadata": {
                    "turn_id": payload.turn_id,
                    "human_message_id": payload.human_message_id,
                    "ui_thread_id": payload.ui_thread_id,
                },
                "stream_mode": ["messages-tuple", "values"],
                "on_disconnect": "continue",
            },
        )
        return {
            "turn_id": payload.turn_id,
            "human_message_id": payload.human_message_id,
            "thread_id": subscription.thread_id,
            "run_id": subscription.run_id,
        }

    @app.post("/threads")
    async def create_thread(
        payload: ThreadCreateRequest, request: Request, response: Response
    ) -> dict[str, Any]:
        thread_id = payload.thread_id or str(uuid4())
        auth = get_auth(request)
        try:
            record = await asyncio.to_thread(
                get_runtime(request).metadata_store.create_thread,
                thread_id,
                metadata=user_scoped_metadata(auth, payload.metadata),
                if_exists=payload.if_exists or "raise",
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        response.headers["Content-Location"] = f"/threads/{record.thread_id}"
        return thread_payload(record)

    @app.get("/threads/{thread_id}")
    async def get_thread(thread_id: str, request: Request) -> dict[str, Any]:
        await authorize_thread(request, thread_id)
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
        await authorize_thread(request, thread_id)
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
        await authorize_thread(request, thread_id)
        thread_record = await asyncio.to_thread(
            get_runtime(request).metadata_store.get_thread, thread_id
        )
        if thread_record is None:
            raise HTTPException(
                status_code=404, detail=f"Thread '{thread_id}' not found"
            )
        try:
            return await get_runtime(request).orchestrator.state(
                thread_id=thread_id, subgraphs=subgraphs
            )
        except Exception as exc:
            _raise_if_missing_checkpointer(
                exc,
                detail="Thread state is unavailable because persistence is disabled",
            )
            raise

    @app.post("/threads/{thread_id}/history")
    async def get_thread_history(
        thread_id: str, payload: ThreadHistoryRequest, request: Request
    ) -> list[dict[str, Any]]:
        await authorize_thread(request, thread_id)
        thread_record = await asyncio.to_thread(
            get_runtime(request).metadata_store.get_thread, thread_id
        )
        if thread_record is None:
            raise HTTPException(
                status_code=404, detail=f"Thread '{thread_id}' not found"
            )
        try:
            return await get_runtime(request).orchestrator.history(
                thread_id=thread_id,
                checkpoint=payload.checkpoint,
                limit=payload.limit,
                before=payload.before,
                metadata_filter=payload.metadata,
            )
        except Exception as exc:
            _raise_if_missing_checkpointer(
                exc,
                detail="Thread history is unavailable because persistence is disabled",
            )
            if _history_fallback_enabled(exc):
                try:
                    snapshot = await get_runtime(request).orchestrator.state(
                        thread_id=thread_id, checkpoint=payload.checkpoint
                    )
                except NotImplementedError:
                    return []
                return [snapshot]
            raise

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
            metadata=user_scoped_metadata(get_auth(request), payload.metadata),
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
                    metadata=user_scoped_metadata(get_auth(request), payload.metadata),
                    if_exists="raise",
                )
            else:
                raise HTTPException(
                    status_code=404, detail=f"Thread '{thread_id}' not found"
                )
        await authorize_thread(request, thread_id)
        return await _start_stream(thread_record.thread_id, payload, request)

    async def _start_stream(
        thread_id: str, payload: StreamRunRequest, request: Request
    ) -> Response:
        runtime = get_runtime(request)
        payload_dict = payload.model_dump()
        payload_dict["interrupt_before"] = None
        payload_dict["interrupt_after"] = None
        if payload_dict.get("multitask_strategy") not in (None, "interrupt"):
            raise HTTPException(
                status_code=422, detail="Unsupported multitask_strategy for MVP1"
            )
        try:
            sub = await runtime.orchestrator.start(
                thread_id=thread_id,
                assistant_id=payload.assistant_id,
                payload=payload_dict,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return sse_response(
            sub.events(), thread_id=thread_id, run_id=sub.run_id
        )

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
        await authorize_thread(request, thread_id)
        run_record = await asyncio.to_thread(
            runtime.metadata_store.get_run, run_id
        )
        if run_record is None or run_record.thread_id != thread_id:
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
        after_id = 0
        if last_event_id and last_event_id != "-1":
            try:
                after_id = int(last_event_id)
            except ValueError as exc:
                raise HTTPException(
                    status_code=422, detail="Invalid Last-Event-ID"
                ) from exc
        sub = await runtime.orchestrator.attach(
            run_id=run_id, thread_id=thread_id
        )
        return sse_response(
            sub.events(
                last_event_id=after_id,
                cancel_on_disconnect=cancel_on_disconnect,
            ),
            thread_id=thread_id,
            run_id=run_id,
        )

    @app.post("/threads/{thread_id}/runs/{run_id}/cancel")
    async def cancel_run(
        thread_id: str, run_id: str, request: Request
    ) -> dict[str, str]:
        runtime = get_runtime(request)
        await authorize_thread(request, thread_id)
        run_record = await asyncio.to_thread(
            runtime.metadata_store.get_run, run_id
        )
        if run_record is None or run_record.thread_id != thread_id:
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
        try:
            status = await runtime.orchestrator.cancel(
                run_id=run_id, thread_id=thread_id
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=404, detail=f"Run '{run_id}' not found"
            ) from exc
        return {
            "status": {
                "error": "failed",
                "completed": "completed",
                "cancelled": "cancelled",
            }.get(status, "failed")
        }

    return app


app = create_app()
