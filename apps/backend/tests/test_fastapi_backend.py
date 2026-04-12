from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langgraph.types import StateSnapshot

from rerai_api.app import create_app
from rerai_api.db import MetadataStore
from rerai_api.runtime import BackendRuntime, SYSTEM_ASSISTANT_ID


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


@pytest.fixture
def client(tmp_path: Path):
    database_uri = f"sqlite:///{tmp_path / 'rerai-test.db'}"
    runtime = BackendRuntime(
        database_uri,
        graph=FakeGraph(),
        metadata_store=MetadataStore(database_uri),
    )
    app = create_app(runtime)
    with TestClient(app) as test_client:
        yield test_client


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
