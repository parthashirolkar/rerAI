from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Protocol


class _Dialect(Protocol):
    @property
    def placeholder(self) -> str: ...

    def setup_statements(self) -> list[str]: ...

    def adapt_json(self, value: Any) -> Any: ...

    def read_json(self, value: Any, fallback: Any) -> Any: ...

    def read_datetime(self, value: Any) -> str: ...

    def adapt_row(self, row: Any) -> dict[str, Any]: ...


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def _json_loads(value: str | None, fallback: Any = None) -> Any:
    if value in (None, ""):
        return fallback
    return json.loads(value)


def _coerce_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return str(value)


class _PostgresDialect:
    @property
    def placeholder(self) -> str:
        return "%s"

    def setup_statements(self) -> list[str]:
        return [
            """
            create table if not exists rerai_threads (
                thread_id uuid primary key,
                metadata jsonb not null default '{}'::jsonb,
                status text not null default 'idle',
                created_at timestamptz not null default now(),
                updated_at timestamptz not null default now(),
                deleted_at timestamptz null
            )
            """,
            """
            create table if not exists rerai_runs (
                run_id uuid primary key,
                thread_id uuid not null references rerai_threads(thread_id) on delete cascade,
                assistant_id text not null,
                status text not null,
                metadata jsonb not null default '{}'::jsonb,
                config jsonb null,
                context jsonb null,
                input_payload jsonb null,
                command_payload jsonb null,
                stream_mode jsonb not null default '[]'::jsonb,
                on_disconnect text not null default 'continue',
                error jsonb null,
                created_at timestamptz not null default now(),
                updated_at timestamptz not null default now(),
                completed_at timestamptz null
            )
            """,
            """
            create table if not exists rerai_run_events (
                run_id uuid not null references rerai_runs(run_id) on delete cascade,
                thread_id uuid not null references rerai_threads(thread_id) on delete cascade,
                stream_id bigint not null,
                event text not null,
                data jsonb null,
                created_at timestamptz not null default now(),
                primary key (run_id, stream_id)
            )
            """,
            """
            create index if not exists rerai_runs_thread_created_idx
            on rerai_runs (thread_id, created_at desc)
            """,
            """
            create index if not exists rerai_run_events_thread_run_stream_idx
            on rerai_run_events (thread_id, run_id, stream_id)
            """,
        ]

    def adapt_json(self, value: Any) -> Any:
        return _json_dumps(value) if value is not None else None

    def read_json(self, value: Any, fallback: Any) -> Any:
        if value is None:
            return fallback
        if isinstance(value, (dict, list)):
            return value
        return _json_loads(value, fallback)

    def read_datetime(self, value: Any) -> str:
        return _coerce_datetime(value)

    def adapt_row(self, row: Any) -> dict[str, Any]:
        return dict(row)


class _SqliteDialect:
    @property
    def placeholder(self) -> str:
        return "?"

    def setup_statements(self) -> list[str]:
        return [
            """
            create table if not exists rerai_threads (
                thread_id text primary key,
                metadata text not null default '{}',
                status text not null default 'idle',
                created_at text not null default current_timestamp,
                updated_at text not null default current_timestamp,
                deleted_at text null
            )
            """,
            """
            create table if not exists rerai_runs (
                run_id text primary key,
                thread_id text not null references rerai_threads(thread_id) on delete cascade,
                assistant_id text not null,
                status text not null,
                metadata text not null default '{}',
                config text null,
                context text null,
                input_payload text null,
                command_payload text null,
                stream_mode text not null default '[]',
                on_disconnect text not null default 'continue',
                error text null,
                created_at text not null default current_timestamp,
                updated_at text not null default current_timestamp,
                completed_at text null
            )
            """,
            """
            create table if not exists rerai_run_events (
                run_id text not null references rerai_runs(run_id) on delete cascade,
                thread_id text not null references rerai_threads(thread_id) on delete cascade,
                stream_id integer not null,
                event text not null,
                data text null,
                created_at text not null default current_timestamp,
                primary key (run_id, stream_id)
            )
            """,
            "create index if not exists rerai_runs_thread_created_idx on rerai_runs (thread_id, created_at desc)",
            "create index if not exists rerai_run_events_thread_run_stream_idx on rerai_run_events (thread_id, run_id, stream_id)",
        ]

    def adapt_json(self, value: Any) -> Any:
        return _json_dumps(value) if value is not None else None

    def read_json(self, value: Any, fallback: Any) -> Any:
        if value is None:
            return fallback
        if isinstance(value, (dict, list)):
            return value
        return _json_loads(value, fallback)

    def read_datetime(self, value: Any) -> str:
        return _coerce_datetime(value)

    def adapt_row(self, row: Any) -> dict[str, Any]:
        return dict(row)
