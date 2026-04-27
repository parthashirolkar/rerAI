from __future__ import annotations

from langchain_core.messages import AIMessage, AIMessageChunk

from rerai_api.adapters.langgraph import (
    graph_stream_modes,
    json_safe,
    normalize_stream_chunk,
)


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


def test_interrupt_shaped_stream_event_serializes_without_error():
    chunk = {"__interrupt__": [{"value": {"action": "test"}}]}
    event, data = normalize_stream_chunk(chunk)
    assert event == "values"
    serialized = json_safe(data)
    assert isinstance(serialized, dict)
    assert "__interrupt__" in serialized
