from __future__ import annotations

import json
import logging
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi.encoders import jsonable_encoder
from langchain_core.messages import BaseMessage
from langchain_core.messages.base import message_to_dict
from langgraph.types import Command, Send, StateSnapshot

from rerai_api.ports import GraphPort

logger = logging.getLogger(__name__)


def json_safe(value: Any) -> Any:
    if isinstance(value, BaseMessage):
        return serialize_message(value)
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


def serialize_message(message: BaseMessage) -> dict[str, Any]:
    raw = message_to_dict(message)
    if not isinstance(raw, dict):
        return {"type": getattr(message, "type", "unknown"), "content": str(message)}

    data = raw.get("data")
    if not isinstance(data, dict):
        return jsonable_encoder(raw)

    payload: dict[str, Any] = {
        "type": str(
            raw.get("type") or data.get("type") or getattr(message, "type", "unknown")
        )
    }
    for key in (
        "content",
        "id",
        "name",
        "tool_calls",
        "invalid_tool_calls",
        "tool_call_id",
        "status",
        "artifact",
        "additional_kwargs",
        "response_metadata",
        "usage_metadata",
    ):
        if key in data and data[key] is not None:
            payload[key] = json_safe(data[key])
    return payload


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


def graph_stream_modes(stream_modes: list[str]) -> list[str]:
    return [
        "messages" if stream_mode == "messages-tuple" else stream_mode
        for stream_mode in stream_modes
    ]


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


def normalize_stream_chunk(chunk: Any) -> tuple[str, Any]:
    if isinstance(chunk, tuple):
        if len(chunk) == 2:
            event, data = chunk
            if isinstance(event, BaseMessage):
                return "messages", chunk
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


class LangGraphAdapter(GraphPort):
    """Adapts a raw LangGraph graph to the framework-agnostic ``GraphPort`` protocol."""

    def __init__(self, graph) -> None:
        self._graph = graph

    async def stream(
        self, *, thread_id: str, assistant_id: str, payload: dict[str, Any]
    ) -> Any:
        stream_modes = parse_stream_modes(payload.get("stream_mode"))
        config = build_runnable_config(thread_id=thread_id, payload=payload)
        input_value = build_graph_input(payload)
        async for chunk in self._graph.astream(
            input_value,
            config=config,
            context=payload.get("context"),
            stream_mode=graph_stream_modes(stream_modes),
            durability=payload.get("durability"),
            subgraphs=bool(payload.get("stream_subgraphs", False)),
        ):
            event_name, data = normalize_stream_chunk(chunk)
            yield event_name, json_safe(data)

    async def get_state(
        self,
        *,
        thread_id: str,
        checkpoint: dict[str, Any] | None = None,
        subgraphs: bool = False,
    ) -> dict[str, Any]:
        config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
        if checkpoint:
            config["configurable"].update(checkpoint)
        snapshot = await self._graph.aget_state(config, subgraphs=subgraphs)
        return format_state_snapshot(snapshot)

    async def get_history(
        self,
        *,
        thread_id: str,
        checkpoint: dict[str, Any] | None = None,
        limit: int = 10,
        before: dict[str, Any] | str | None = None,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
        if checkpoint:
            config["configurable"].update(checkpoint)
        before_config = None
        if before is not None:
            before_configurable: dict[str, Any] = {"thread_id": thread_id}
            if isinstance(before, str):
                before_configurable["checkpoint_id"] = before
            else:
                before_configurable.update(before)
            before_config = {"configurable": before_configurable}
        history = self._graph.aget_state_history(
            config,
            filter=metadata_filter,
            before=before_config,
            limit=limit,
        )
        return [format_state_snapshot(snapshot) async for snapshot in history]
