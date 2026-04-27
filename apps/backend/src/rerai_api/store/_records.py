from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ThreadRecord:
    thread_id: str
    metadata: dict[str, Any]
    status: str
    created_at: str
    updated_at: str
    deleted_at: str | None = None


@dataclass(frozen=True, slots=True)
class RunRecord:
    run_id: str
    thread_id: str
    assistant_id: str
    status: str
    metadata: dict[str, Any]
    config: dict[str, Any] | None
    context: dict[str, Any] | None
    input_payload: Any
    command_payload: dict[str, Any] | None
    stream_mode: list[str]
    on_disconnect: str
    created_at: str
    updated_at: str
    completed_at: str | None = None
    error: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class RunEventRecord:
    run_id: str
    thread_id: str
    stream_id: int
    event: str
    data: Any
    created_at: str
