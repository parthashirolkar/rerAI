from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langgraph.types import StateSnapshot

from rerai_api.app import create_app
from rerai_api.convex import ConvexUser
from rerai_api.store import Store

from rerai_api.runtime import (
    BackendRuntime,
    SYSTEM_ASSISTANT_ID,
)


class FakeGraph:
    def __init__(self) -> None:
        self.stream_calls = 0
        self.state = StateSnapshot(
            values={"messages": [{"type": "human", "content": "hello"}]},
            next=(),
            config={"configurable": {"thread_id": "unused", "checkpoint_id": "cp-1"}},
            metadata={"run_id": "run-1"},
            created_at="2026-04-13T00:00:00+00:00",
            parent_config=None,
            tasks=(),
            interrupts=(),
        )

    async def astream(self, input, config=None, **kwargs):
        self.stream_calls += 1
        yield ("values", {"messages": input["messages"]})
        yield (
            "values",
            {"messages": input["messages"] + [{"type": "ai", "content": "done"}]},
        )

    async def aget_state(self, config, *, subgraphs=False):
        return StateSnapshot(
            values={"messages": [{"type": "human", "content": "hello"}]},
            next=(),
            config={
                "configurable": {
                    "thread_id": config["configurable"]["thread_id"],
                    "checkpoint_id": "cp-1",
                }
            },
            metadata={"run_id": "run-1"},
            created_at="2026-04-13T00:00:00+00:00",
            parent_config=None,
            tasks=(),
            interrupts=(),
        )

    async def aget_state_history(self, config, *, filter=None, before=None, limit=None):
        yield await self.aget_state(config)

    def get_input_jsonschema(self):
        return {"type": "object"}

    def get_output_jsonschema(self):
        return {"type": "object"}

    def config_schema(self):
        class ConfigModel:
            @staticmethod
            def model_json_schema():
                return {"type": "object"}

        return ConfigModel()

    def get_context_jsonschema(self):
        return {"type": "object"}


class NoCheckpointerGraph(FakeGraph):
    async def aget_state(self, config, *, subgraphs=False):
        raise ValueError("No checkpointer set")

    async def aget_state_history(self, config, *, filter=None, before=None, limit=None):
        if False:
            yield None
        raise ValueError("No checkpointer set")


class LangChainMessageGraph(FakeGraph):
    async def astream(self, input, config=None, **kwargs):
        yield ("values", {"messages": [HumanMessage(content="hello")]})
        yield (
            "values",
            {
                "messages": [
                    HumanMessage(content="hello"),
                    AIMessage(content="done", id="ai-1"),
                ]
            },
        )


class MessageTupleGraph(FakeGraph):
    def __init__(self) -> None:
        super().__init__()
        self.stream_modes: list[list[str]] = []

    async def astream(self, input, config=None, **kwargs):
        self.stream_modes.append(list(kwargs.get("stream_mode") or []))
        yield (
            "messages",
            (AIMessageChunk(content="partial", id="ai-1"), {"langgraph_node": "agent"}),
        )
        yield (
            "values",
            {"messages": input["messages"] + [AIMessage(content="done", id="ai-1")]},
        )


class FinalStateGraph(FakeGraph):
    def __init__(self) -> None:
        super().__init__()
        self.messages = []

    async def astream(self, input, config=None, **kwargs):
        self.stream_calls += 1
        self.messages = [
            *input["messages"],
            AIMessage(content="Researching the site.", id="ai-progress"),
            AIMessage(content="Final assessment.", id="ai-final"),
        ]
        yield ("values", {"messages": self.messages})

    async def aget_state(self, config, *, subgraphs=False):
        return StateSnapshot(
            values={"messages": self.messages},
            next=(),
            config={
                "configurable": {
                    "thread_id": config["configurable"]["thread_id"],
                    "checkpoint_id": "cp-final",
                }
            },
            metadata={"turn_id": "turn-1"},
            created_at="2026-04-13T00:00:00+00:00",
            parent_config=None,
            tasks=(),
            interrupts=(),
        )


class BlockingGraph(FakeGraph):
    async def astream(self, input, config=None, **kwargs):
        self.stream_calls += 1
        await asyncio.Event().wait()
        if False:
            yield None


class PartialThenBlockingGraph(FakeGraph):
    async def astream(self, input, config=None, **kwargs):
        self.stream_calls += 1
        yield (
            "messages",
            (
                AIMessageChunk(content="Partial assessment", id="ai-partial"),
                {"langgraph_node": "agent"},
            ),
        )
        await asyncio.Event().wait()

    async def aget_state(self, config, *, subgraphs=False):
        return StateSnapshot(
            values={
                "messages": [
                    {
                        "type": "human",
                        "id": "human-1",
                        "content": "Check Survey No. 45/2",
                    }
                ]
            },
            next=(),
            config={
                "configurable": {
                    "thread_id": config["configurable"]["thread_id"],
                    "checkpoint_id": "cp-before-partial",
                }
            },
            metadata={"turn_id": "turn-1"},
            created_at="2026-04-13T00:00:00+00:00",
            parent_config=None,
            tasks=(),
            interrupts=(),
        )


class FakeConvexClient:
    def __init__(self) -> None:
        self.turns: dict[str, dict] = {}
        self.finalizations: list[dict] = []

    async def get_viewer(self, token: str):
        if token == "test-token":
            return ConvexUser(user_id="test-user", token_identifier="token:test")
        if token == "other-token":
            return ConvexUser(user_id="other-user", token_identifier="token:other")
        return None

    async def owns_langgraph_thread(self, token: str, thread_id: str) -> bool:
        return False

    async def ensure_turn(
        self,
        token: str,
        *,
        ui_thread_id: str,
        turn_id: str,
        human_message_id: str,
        content: str,
    ) -> dict:
        turn = self.turns.setdefault(
            turn_id,
            {
                "uiThreadId": ui_thread_id,
                "turnId": turn_id,
                "humanMessageId": human_message_id,
                "content": content,
                "status": "pending",
            },
        )
        return turn

    async def mark_turn_running(
        self,
        token: str,
        *,
        turn_id: str,
        langgraph_thread_id: str,
        langgraph_run_id: str,
    ) -> dict:
        turn = self.turns[turn_id]
        turn.update(
            {
                "status": "running",
                "langgraphThreadId": langgraph_thread_id,
                "langgraphRunId": langgraph_run_id,
            }
        )
        return turn

    async def finalize_turn(self, payload: dict) -> None:
        self.finalizations.append(payload)


class FailingFinalizationConvexClient(FakeConvexClient):
    async def finalize_turn(self, payload: dict) -> None:
        raise RuntimeError("Convex unavailable")


@pytest.fixture
def client(tmp_path: Path):
    database_uri = f"sqlite:///{tmp_path / 'rerai-test.db'}"
    runtime = BackendRuntime(
        database_uri,
        graph=FakeGraph(),
        metadata_store=Store(database_uri),
    )
    app = create_app(runtime, convex_client=FakeConvexClient())
    with TestClient(app) as test_client:
        test_client.headers.update({"Authorization": "Bearer test-token"})
        yield test_client


def test_requires_bearer_token(tmp_path: Path):
    database_uri = f"sqlite:///{tmp_path / 'rerai-test-auth.db'}"
    runtime = BackendRuntime(
        database_uri,
        graph=FakeGraph(),
        metadata_store=Store(database_uri),
    )
    app = create_app(runtime, convex_client=FakeConvexClient())
    with TestClient(app) as test_client:
        ok = test_client.get("/ok")
        assert ok.status_code == 200

        blocked = test_client.get("/info")
        assert blocked.status_code == 401

        allowed = test_client.get(
            "/info",
            headers={"Authorization": "Bearer test-token"},
        )
        assert allowed.status_code == 200


def test_assistant_resolution(client: TestClient):
    response = client.get("/assistants/rerai")
    assert response.status_code == 200
    assert response.json()["assistant_id"] == SYSTEM_ASSISTANT_ID

    uuid_response = client.get(f"/assistants/{SYSTEM_ASSISTANT_ID}")
    assert uuid_response.status_code == 200

    missing = client.get("/assistants/missing")
    assert missing.status_code == 404


def test_thread_lifecycle(client: TestClient):
    created = client.post("/threads", json={})
    assert created.status_code == 200
    thread_id = created.json()["thread_id"]

    fetched = client.get(f"/threads/{thread_id}")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "idle"

    deleted = client.delete(f"/threads/{thread_id}")
    assert deleted.status_code == 204

    missing = client.get(f"/threads/{thread_id}")
    assert missing.status_code == 404


def test_state_and_history(client: TestClient):
    created = client.post("/threads", json={})
    thread_id = created.json()["thread_id"]

    state = client.get(f"/threads/{thread_id}/state")
    assert state.status_code == 200
    assert state.json()["values"]["messages"][0]["content"] == "hello"

    history = client.post(f"/threads/{thread_id}/history", json={"limit": 5})
    assert history.status_code == 200
    assert history.json()[0]["checkpoint"]["checkpoint_id"] == "cp-1"


def test_thread_access_rejects_different_user(client: TestClient):
    created = client.post("/threads", json={})
    thread_id = created.json()["thread_id"]

    response = client.get(
        f"/threads/{thread_id}/state",
        headers={"Authorization": "Bearer other-token"},
    )

    assert response.status_code == 403


def test_stream_protocol_and_reconnect(client: TestClient):
    created = client.post("/threads", json={})
    thread_id = created.json()["thread_id"]

    with client.stream(
        "POST",
        f"/threads/{thread_id}/runs/stream",
        json={
            "assistant_id": "rerai",
            "input": {"messages": [{"type": "human", "content": "hello"}]},
            "stream_mode": ["values"],
            "stream_resumable": True,
            "on_disconnect": "continue",
        },
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-location"].startswith(
            f"/threads/{thread_id}/runs/"
        )
        text = "".join(response.iter_text())

    assert "event: metadata" in text
    assert "event: values" in text
    assert "event: end" in text

    run_id = response.headers["content-location"].split("/")[-1]

    joined = client.get(
        f"/threads/{thread_id}/runs/{run_id}/stream",
        headers={"Last-Event-ID": "1"},
    )
    assert joined.status_code == 200
    assert "event: end" in joined.text


def test_turn_submission_is_idempotent_by_turn_id(tmp_path: Path):
    database_uri = f"sqlite:///{tmp_path / 'rerai-turn-submit.db'}"
    graph = FakeGraph()
    convex_client = FakeConvexClient()
    runtime = BackendRuntime(
        database_uri,
        graph=graph,
        metadata_store=Store(database_uri),
    )
    app = create_app(runtime, convex_client=convex_client)

    payload = {
        "turnId": "turn-1",
        "humanMessageId": "human-1",
        "uiThreadId": "ui-thread-1",
        "content": "Check Survey No. 45/2",
    }

    with TestClient(app) as test_client:
        test_client.headers.update({"Authorization": "Bearer test-token"})

        first = test_client.post("/chat/turns", json=payload)
        second = test_client.post("/chat/turns", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json()
    assert first.json()["turn_id"] == "turn-1"
    assert first.json()["human_message_id"] == "human-1"
    assert first.json()["run_id"]
    assert first.json()["thread_id"]
    assert graph.stream_calls == 1


def test_turn_submission_rejects_reused_turn_id_with_different_request(
    tmp_path: Path,
):
    database_uri = f"sqlite:///{tmp_path / 'rerai-turn-conflict.db'}"
    runtime = BackendRuntime(
        database_uri,
        graph=FakeGraph(),
        metadata_store=Store(database_uri),
    )
    app = create_app(runtime, convex_client=FakeConvexClient())

    with TestClient(app) as test_client:
        test_client.headers.update({"Authorization": "Bearer test-token"})
        first = test_client.post(
            "/chat/turns",
            json={
                "turnId": "turn-1",
                "humanMessageId": "human-1",
                "uiThreadId": "ui-thread-1",
                "content": "Check Survey No. 45/2",
            },
        )
        conflict = test_client.post(
            "/chat/turns",
            json={
                "turnId": "turn-1",
                "humanMessageId": "human-2",
                "uiThreadId": "ui-thread-1",
                "content": "Check a different site",
            },
        )

    assert first.status_code == 200
    assert conflict.status_code == 409


def test_completed_turn_is_finalized_from_canonical_state(tmp_path: Path):
    database_uri = f"sqlite:///{tmp_path / 'rerai-turn-finalize.db'}"
    convex_client = FakeConvexClient()
    runtime = BackendRuntime(
        database_uri,
        graph=FinalStateGraph(),
        metadata_store=Store(database_uri),
    )
    app = create_app(runtime, convex_client=convex_client)

    with TestClient(app) as test_client:
        test_client.headers.update({"Authorization": "Bearer test-token"})
        submitted = test_client.post(
            "/chat/turns",
            json={
                "turnId": "turn-1",
                "humanMessageId": "human-1",
                "uiThreadId": "ui-thread-1",
                "content": "Check Survey No. 45/2",
            },
        )
        result = submitted.json()
        joined = test_client.get(
            f"/threads/{result['thread_id']}/runs/{result['run_id']}/stream"
        )

    assert joined.status_code == 200
    assert convex_client.finalizations == [
        {
            "finalizationId": result["run_id"],
            "turnId": "turn-1",
            "status": "completed",
            "assistantMessages": [
                {
                    "messageId": "ai-progress",
                    "langgraphMessageId": "ai-progress",
                    "messagePosition": 0,
                    "canonicalContent": "Researching the site.",
                },
                {
                    "messageId": "ai-final",
                    "langgraphMessageId": "ai-final",
                    "messagePosition": 1,
                    "canonicalContent": "Final assessment.",
                },
            ],
        }
    ]


def test_cancel_run_is_explicit_and_idempotent(tmp_path: Path):
    database_uri = f"sqlite:///{tmp_path / 'rerai-turn-cancel.db'}"
    runtime = BackendRuntime(
        database_uri,
        graph=BlockingGraph(),
        metadata_store=Store(database_uri),
    )
    app = create_app(runtime, convex_client=FakeConvexClient())

    with TestClient(app) as test_client:
        test_client.headers.update({"Authorization": "Bearer test-token"})
        submitted = test_client.post(
            "/chat/turns",
            json={
                "turnId": "turn-1",
                "humanMessageId": "human-1",
                "uiThreadId": "ui-thread-1",
                "content": "Check Survey No. 45/2",
            },
        ).json()
        path = (
            f"/threads/{submitted['thread_id']}/runs/{submitted['run_id']}/cancel"
        )

        first = test_client.post(path)
        second = test_client.post(path)

    assert first.status_code == 200
    assert first.json() == {"status": "cancelled"}
    assert second.status_code == 200
    assert second.json() == {"status": "cancelled"}


def test_cancelled_turn_preserves_uncheckpointed_text_as_display_only(
    tmp_path: Path,
):
    database_uri = f"sqlite:///{tmp_path / 'rerai-turn-cancel-partial.db'}"
    convex_client = FakeConvexClient()
    store = Store(database_uri)
    runtime = BackendRuntime(
        database_uri,
        graph=PartialThenBlockingGraph(),
        metadata_store=store,
    )
    app = create_app(runtime, convex_client=convex_client)

    with TestClient(app) as test_client:
        test_client.headers.update({"Authorization": "Bearer test-token"})
        submitted = test_client.post(
            "/chat/turns",
            json={
                "turnId": "turn-1",
                "humanMessageId": "human-1",
                "uiThreadId": "ui-thread-1",
                "content": "Check Survey No. 45/2",
            },
        ).json()
        for _ in range(100):
            if any(
                event.event == "messages"
                for event in store.list_events(submitted["run_id"])
            ):
                break
            time.sleep(0.01)

        cancelled = test_client.post(
            f"/threads/{submitted['thread_id']}/runs/{submitted['run_id']}/cancel"
        )

    assert cancelled.json() == {"status": "cancelled"}
    assert convex_client.finalizations[-1]["assistantMessages"] == [
        {
            "messageId": "ai-partial",
            "langgraphMessageId": "ai-partial",
            "messagePosition": 0,
            "canonicalContent": "",
            "displayOnlyContent": "Partial assessment",
        }
    ]


def test_failed_projection_replays_from_durable_outbox_after_restart(
    tmp_path: Path,
):
    database_uri = f"sqlite:///{tmp_path / 'rerai-turn-outbox.db'}"
    first_runtime = BackendRuntime(
        database_uri,
        graph=FinalStateGraph(),
        metadata_store=Store(database_uri),
    )
    first_app = create_app(
        first_runtime,
        convex_client=FailingFinalizationConvexClient(),
    )

    with TestClient(first_app) as test_client:
        test_client.headers.update({"Authorization": "Bearer test-token"})
        submitted = test_client.post(
            "/chat/turns",
            json={
                "turnId": "turn-1",
                "humanMessageId": "human-1",
                "uiThreadId": "ui-thread-1",
                "content": "Check Survey No. 45/2",
            },
        ).json()
        test_client.get(
            f"/threads/{submitted['thread_id']}/runs/{submitted['run_id']}/stream"
        )

    recovering_client = FakeConvexClient()
    second_runtime = BackendRuntime(
        database_uri,
        graph=FakeGraph(),
        metadata_store=Store(database_uri),
    )
    second_app = create_app(second_runtime, convex_client=recovering_client)
    with TestClient(second_app):
        pass

    assert len(recovering_client.finalizations) == 1
    assert recovering_client.finalizations[0]["turnId"] == "turn-1"
    assert recovering_client.finalizations[0]["status"] == "completed"


def test_startup_terminalizes_orphaned_running_turn(tmp_path: Path):
    database_uri = f"sqlite:///{tmp_path / 'rerai-turn-orphan.db'}"
    store = Store(database_uri)
    store.setup()
    thread = store.create_thread(
        metadata={"convex_user_id": "test-user", "ui_thread_id": "ui-thread-1"}
    )
    run = store.create_run(
        thread_id=thread.thread_id,
        metadata={
            "turn_id": "turn-1",
            "human_message_id": "human-1",
            "ui_thread_id": "ui-thread-1",
        },
        input_payload={
            "messages": [
                {
                    "type": "human",
                    "id": "human-1",
                    "content": "Check Survey No. 45/2",
                }
            ]
        },
    )
    convex_client = FakeConvexClient()
    runtime = BackendRuntime(
        database_uri,
        graph=FakeGraph(),
        metadata_store=Store(database_uri),
    )
    app = create_app(runtime, convex_client=convex_client)

    with TestClient(app):
        pass

    assert runtime.metadata_store.get_run(run.run_id).status == "error"
    assert convex_client.finalizations[0]["turnId"] == "turn-1"
    assert convex_client.finalizations[0]["status"] == "failed"


def test_stream_serializes_real_langchain_messages(tmp_path: Path):
    database_uri = f"sqlite:///{tmp_path / 'rerai-test-stream.db'}"
    runtime = BackendRuntime(
        database_uri,
        graph=LangChainMessageGraph(),
        metadata_store=Store(database_uri),
    )
    app = create_app(runtime, convex_client=FakeConvexClient())
    with TestClient(app) as test_client:
        test_client.headers.update({"Authorization": "Bearer test-token"})
        created = test_client.post("/threads", json={})
        thread_id = created.json()["thread_id"]

        with test_client.stream(
            "POST",
            f"/threads/{thread_id}/runs/stream",
            json={
                "assistant_id": "rerai",
                "input": {"messages": [{"type": "human", "content": "hello"}]},
                "stream_mode": ["values"],
                "stream_resumable": True,
                "on_disconnect": "continue",
            },
        ) as response:
            assert response.status_code == 200
            text = "".join(response.iter_text())

    assert '"type":"ai"' in text
    assert '"content":"done"' in text
    assert '"id":"ai-1"' in text


def test_stream_accepts_sdk_messages_tuple_mode(tmp_path: Path):
    database_uri = f"sqlite:///{tmp_path / 'rerai-test-messages-tuple.db'}"
    graph = MessageTupleGraph()
    runtime = BackendRuntime(
        database_uri,
        graph=graph,
        metadata_store=Store(database_uri),
    )
    app = create_app(runtime, convex_client=FakeConvexClient())
    with TestClient(app) as test_client:
        test_client.headers.update({"Authorization": "Bearer test-token"})
        created = test_client.post("/threads", json={})
        thread_id = created.json()["thread_id"]

        with test_client.stream(
            "POST",
            f"/threads/{thread_id}/runs/stream",
            json={
                "assistant_id": "rerai",
                "input": {"messages": [{"type": "human", "content": "hello"}]},
                "stream_mode": ["messages-tuple", "values"],
                "stream_resumable": True,
                "on_disconnect": "continue",
            },
        ) as response:
            assert response.status_code == 200
            text = "".join(response.iter_text())

    assert graph.stream_modes == [["messages", "values"]]
    assert "event: messages" in text
    assert "event: values" in text
    assert "event: end" in text
    assert '"langgraph_node":"agent"' in text
    assert '"message_position":0' in text
    assert "messages-tuple" not in text


def test_unsupported_stream_fields_return_422(client: TestClient):
    created = client.post("/threads", json={})
    thread_id = created.json()["thread_id"]

    response = client.post(
        f"/threads/{thread_id}/runs/stream",
        json={
            "assistant_id": "rerai",
            "input": {"messages": [{"type": "human", "content": "hello"}]},
            "webhook": "https://example.com",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_runtime_setup_builds_graph_with_persistence(monkeypatch, tmp_path: Path):
    database_uri = f"sqlite:///{tmp_path / 'rerai-runtime.db'}"
    persisted_graph = object()
    calls: list[str] = []

    class FakeAgentHub:
        def __init__(self, **kwargs) -> None:
            self._database_uri = kwargs.get("database_uri") or ""

        async def setup(self) -> None:
            calls.append(self._database_uri)

        @property
        def graph(self):
            return persisted_graph

        @classmethod
        async def production(cls, *, database_uri: str | None = None, **kwargs):
            hub = cls(database_uri=database_uri)
            await hub.setup()
            return hub

    import rerai_api.runtime as runtime_module

    monkeypatch.setattr(runtime_module, "AgentHub", FakeAgentHub)
    metadata_store = Store.memory()

    runtime = BackendRuntime(database_uri, metadata_store=metadata_store)

    await runtime.setup()

    assert runtime.graph is persisted_graph
    assert runtime.hub is not None
    assert runtime.orchestrator is not None
    assert calls == [database_uri]
    # Store.memory() should have set up tables without error
    metadata_store.setup()


def test_state_without_checkpointer_returns_503(tmp_path: Path):
    database_uri = f"sqlite:///{tmp_path / 'rerai-state-error.db'}"
    runtime = BackendRuntime(
        database_uri,
        graph=NoCheckpointerGraph(),
        metadata_store=Store(database_uri),
    )
    app = create_app(runtime, convex_client=FakeConvexClient())

    with TestClient(app) as test_client:
        test_client.headers.update({"Authorization": "Bearer test-token"})
        created = test_client.post("/threads", json={})
        thread_id = created.json()["thread_id"]

        state = test_client.get(f"/threads/{thread_id}/state")
        assert state.status_code == 503
        assert "persistence is disabled" in state.json()["detail"]


def test_history_without_checkpointer_returns_503(tmp_path: Path):
    database_uri = f"sqlite:///{tmp_path / 'rerai-history-error.db'}"
    runtime = BackendRuntime(
        database_uri,
        graph=NoCheckpointerGraph(),
        metadata_store=Store(database_uri),
    )
    app = create_app(runtime, convex_client=FakeConvexClient())

    with TestClient(app) as test_client:
        test_client.headers.update({"Authorization": "Bearer test-token"})
        created = test_client.post("/threads", json={})
        thread_id = created.json()["thread_id"]

        history = test_client.post(f"/threads/{thread_id}/history", json={"limit": 5})
        assert history.status_code == 503
        assert "persistence is disabled" in history.json()["detail"]


def test_default_graph_has_no_hitl_interrupts(monkeypatch):
    import rerai_agent.hub as hub_module

    calls = []

    def fake_create_deep_agent(*, interrupt_on=None, **kwargs):
        calls.append(interrupt_on)
        return object()

    monkeypatch.setattr(hub_module, "create_deep_agent", fake_create_deep_agent)
    hub_module.build_graph()
    assert calls == [None]
