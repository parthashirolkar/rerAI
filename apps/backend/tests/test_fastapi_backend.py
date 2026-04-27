from __future__ import annotations

import sys
from types import ModuleType
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langgraph.types import StateSnapshot

from rerai_api.app import create_app
from rerai_api.convex import ConvexUser
from rerai_api.db import MetadataStore
from rerai_api.runtime import (
    BackendRuntime,
    SYSTEM_ASSISTANT_ID,
    graph_stream_modes,
    json_safe,
    normalize_stream_chunk,
)


class FakeGraph:
    def __init__(self) -> None:
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


class StubMetadataStore:
    def __init__(self) -> None:
        self.setup_calls = 0

    def setup(self) -> None:
        self.setup_calls += 1


class FakeConvexClient:
    async def get_viewer(self, token: str):
        if token == "test-token":
            return ConvexUser(user_id="test-user", token_identifier="token:test")
        if token == "other-token":
            return ConvexUser(user_id="other-user", token_identifier="token:other")
        return None

    async def owns_langgraph_thread(self, token: str, thread_id: str) -> bool:
        return False


@pytest.fixture
def client(tmp_path: Path):
    database_uri = f"sqlite:///{tmp_path / 'rerai-test.db'}"
    runtime = BackendRuntime(
        database_uri,
        graph=FakeGraph(),
        metadata_store=MetadataStore(database_uri),
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
        metadata_store=MetadataStore(database_uri),
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


def test_json_safe_flattens_langchain_messages():
    payload = json_safe(AIMessage(content="done", id="ai-1"))
    assert payload["type"] == "ai"
    assert payload["content"] == "done"
    assert payload["id"] == "ai-1"
    assert "data" not in payload


def test_normalize_stream_chunk_treats_raw_message_tuple_as_messages_event():
    event, data = normalize_stream_chunk(
        (AIMessageChunk(content="partial", id="ai-1"), {"langgraph_node": "agent"})
    )

    assert event == "messages"
    serialized = json_safe(data)
    assert serialized[0]["type"] == "AIMessageChunk"
    assert serialized[0]["content"] == "partial"
    assert serialized[0]["id"] == "ai-1"
    assert serialized[1] == {"langgraph_node": "agent"}


def test_graph_stream_modes_translate_messages_tuple_for_python_langgraph():
    assert graph_stream_modes(["messages-tuple", "values"]) == ["messages", "values"]


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


def test_stream_serializes_real_langchain_messages(tmp_path: Path):
    database_uri = f"sqlite:///{tmp_path / 'rerai-test-stream.db'}"
    runtime = BackendRuntime(
        database_uri,
        graph=LangChainMessageGraph(),
        metadata_store=MetadataStore(database_uri),
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
        metadata_store=MetadataStore(database_uri),
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
async def test_runtime_setup_builds_graph_with_persistence(
    monkeypatch, tmp_path: Path
):
    database_uri = f"sqlite:///{tmp_path / 'rerai-runtime.db'}"
    persisted_graph = object()
    fake_module = ModuleType("rerai_agent.graph")
    calls: list[str] = []

    async def fake_build_persisted_graph_async(
        *, database_uri: str | None = None, **kwargs
    ):
        calls.append(database_uri or "")
        return persisted_graph

    fake_module.build_persisted_graph_async = fake_build_persisted_graph_async
    monkeypatch.setitem(sys.modules, "rerai_agent.graph", fake_module)
    metadata_store = StubMetadataStore()

    runtime = BackendRuntime(database_uri, metadata_store=metadata_store)

    await runtime.setup()

    assert runtime.graph is persisted_graph
    assert runtime.run_manager is not None
    assert calls == [database_uri]
    assert metadata_store.setup_calls == 1


def test_state_without_checkpointer_returns_503(tmp_path: Path):
    database_uri = f"sqlite:///{tmp_path / 'rerai-state-error.db'}"
    runtime = BackendRuntime(
        database_uri,
        graph=NoCheckpointerGraph(),
        metadata_store=MetadataStore(database_uri),
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
        metadata_store=MetadataStore(database_uri),
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
    import rerai_agent.graph as graph_module

    calls = []

    def fake_create_deep_agent(*, interrupt_on=None, **kwargs):
        calls.append(interrupt_on)
        return object()

    monkeypatch.setattr(graph_module, "create_deep_agent", fake_create_deep_agent)
    graph_module.build_graph()
    assert calls == [None]


def test_interrupt_shaped_stream_event_serializes_without_error():
    from rerai_api.runtime import normalize_stream_chunk, json_safe

    chunk = {"__interrupt__": [{"value": {"action": "test"}}]}
    event, data = normalize_stream_chunk(chunk)
    assert event == "values"
    serialized = json_safe(data)
    assert isinstance(serialized, dict)
    assert "__interrupt__" in serialized
