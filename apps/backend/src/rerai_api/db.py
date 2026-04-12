from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def _is_postgres_uri(value: str) -> bool:
    lowered = value.strip().lower()
    return lowered.startswith("postgresql://") or lowered.startswith("postgres://")


def _is_sqlite_uri(value: str) -> bool:
    return value.strip().lower().startswith("sqlite://")


def normalize_sqlite_path(value: str) -> str:
    if not _is_sqlite_uri(value):
        return value

    path = value[len("sqlite://") :]
    if path.startswith("/"):
        return path
    return str((Path.cwd() / path).resolve())


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def json_loads(value: str | None, fallback: Any = None) -> Any:
    if value in (None, ""):
        return fallback
    return json.loads(value)


@dataclass(slots=True)
class ThreadRecord:
    thread_id: str
    metadata: dict[str, Any]
    status: str
    created_at: str
    updated_at: str
    deleted_at: str | None = None


@dataclass(slots=True)
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


@dataclass(slots=True)
class RunEventRecord:
    run_id: str
    thread_id: str
    stream_id: int
    event: str
    data: Any
    created_at: str


class MetadataStore:
    def __init__(self, database_uri: str):
        self.database_uri = database_uri.strip()
        self.backend = "postgres" if _is_postgres_uri(self.database_uri) else "sqlite"
        self.sqlite_path = normalize_sqlite_path(self.database_uri)

    @contextmanager
    def connect(self):
        if self.backend == "postgres":
            conn = psycopg.connect(self.database_uri, row_factory=dict_row)
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
            return

        path = Path(self.sqlite_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def setup(self) -> None:
        with self.connect() as conn:
            cursor = conn.cursor()
            if self.backend == "postgres":
                cursor.execute(
                    """
                    create table if not exists rerai_threads (
                        thread_id uuid primary key,
                        metadata jsonb not null default '{}'::jsonb,
                        status text not null default 'idle',
                        created_at timestamptz not null default now(),
                        updated_at timestamptz not null default now(),
                        deleted_at timestamptz null
                    )
                    """
                )
                cursor.execute(
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
                    """
                )
                cursor.execute(
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
                    """
                )
                cursor.execute(
                    """
                    create index if not exists rerai_runs_thread_created_idx
                    on rerai_runs (thread_id, created_at desc)
                    """
                )
                cursor.execute(
                    """
                    create index if not exists rerai_run_events_thread_run_stream_idx
                    on rerai_run_events (thread_id, run_id, stream_id)
                    """
                )
            else:
                cursor.execute(
                    """
                    create table if not exists rerai_threads (
                        thread_id text primary key,
                        metadata text not null default '{}',
                        status text not null default 'idle',
                        created_at text not null default current_timestamp,
                        updated_at text not null default current_timestamp,
                        deleted_at text null
                    )
                    """
                )
                cursor.execute(
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
                    """
                )
                cursor.execute(
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
                    """
                )
                cursor.execute(
                    "create index if not exists rerai_runs_thread_created_idx on rerai_runs (thread_id, created_at desc)"
                )
                cursor.execute(
                    "create index if not exists rerai_run_events_thread_run_stream_idx on rerai_run_events (thread_id, run_id, stream_id)"
                )

    def create_thread(
        self,
        thread_id: str,
        metadata: dict[str, Any] | None = None,
        *,
        if_exists: str = "raise",
    ) -> ThreadRecord:
        metadata = metadata or {}
        now = utc_now().isoformat()
        with self.connect() as conn:
            existing = self._fetch_thread(conn, thread_id, include_deleted=True)
            if existing and existing.deleted_at is None:
                if if_exists == "do_nothing":
                    return existing
                raise ValueError(f"Thread {thread_id} already exists")
            if existing and existing.deleted_at is not None:
                self._execute(
                    conn,
                    """
                    update rerai_threads
                    set metadata = %s, status = %s, created_at = %s, updated_at = %s, deleted_at = null
                    where thread_id = %s
                    """,
                    self._json(metadata),
                    "idle",
                    now,
                    now,
                    thread_id,
                )
            else:
                self._execute(
                    conn,
                    """
                    insert into rerai_threads (thread_id, metadata, status, created_at, updated_at)
                    values (%s, %s, %s, %s, %s)
                    """,
                    thread_id,
                    self._json(metadata),
                    "idle",
                    now,
                    now,
                )
            return self.get_thread(thread_id, include_deleted=True, conn=conn)

    def get_thread(
        self,
        thread_id: str,
        *,
        include_deleted: bool = False,
        conn=None,
    ) -> ThreadRecord | None:
        if conn is not None:
            return self._fetch_thread(conn, thread_id, include_deleted=include_deleted)
        with self.connect() as next_conn:
            return self._fetch_thread(
                next_conn, thread_id, include_deleted=include_deleted
            )

    def delete_thread(self, thread_id: str) -> bool:
        now = utc_now().isoformat()
        with self.connect() as conn:
            record = self._fetch_thread(conn, thread_id, include_deleted=False)
            if record is None:
                return False
            self._execute(
                conn,
                """
                update rerai_threads
                set deleted_at = %s, updated_at = %s, status = %s
                where thread_id = %s
                """,
                now,
                now,
                "deleted",
                thread_id,
            )
            self._execute(
                conn, "delete from rerai_run_events where thread_id = %s", thread_id
            )
            self._execute(
                conn, "delete from rerai_runs where thread_id = %s", thread_id
            )
            return True

    def set_thread_status(self, thread_id: str, status: str) -> None:
        now = utc_now().isoformat()
        with self.connect() as conn:
            self._execute(
                conn,
                "update rerai_threads set status = %s, updated_at = %s where thread_id = %s and deleted_at is null",
                status,
                now,
                thread_id,
            )

    def create_run(
        self,
        *,
        run_id: str,
        thread_id: str,
        assistant_id: str,
        metadata: dict[str, Any] | None,
        config: dict[str, Any] | None,
        context: dict[str, Any] | None,
        input_payload: Any,
        command_payload: dict[str, Any] | None,
        stream_mode: list[str],
        on_disconnect: str,
    ) -> RunRecord:
        now = utc_now().isoformat()
        with self.connect() as conn:
            self._execute(
                conn,
                """
                insert into rerai_runs (
                    run_id, thread_id, assistant_id, status, metadata, config, context,
                    input_payload, command_payload, stream_mode, on_disconnect, created_at, updated_at
                ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                run_id,
                thread_id,
                assistant_id,
                "running",
                self._json(metadata or {}),
                self._json(config),
                self._json(context),
                self._json(input_payload),
                self._json(command_payload),
                self._json(stream_mode),
                on_disconnect,
                now,
                now,
            )
            self._execute(
                conn,
                "update rerai_threads set status = %s, updated_at = %s where thread_id = %s and deleted_at is null",
                "busy",
                now,
                thread_id,
            )
            return self.get_run(run_id, thread_id=thread_id, conn=conn)

    def get_run(
        self, run_id: str, *, thread_id: str | None = None, conn=None
    ) -> RunRecord | None:
        if conn is None:
            with self.connect() as next_conn:
                return self.get_run(run_id, thread_id=thread_id, conn=next_conn)

        sql = "select * from rerai_runs where run_id = %s"
        params: list[Any] = [run_id]
        if thread_id is not None:
            sql += " and thread_id = %s"
            params.append(thread_id)
        row = self._fetchone(conn, sql, *params)
        if row is None:
            return None
        return self._row_to_run(row)

    def finish_run(
        self,
        *,
        run_id: str,
        thread_id: str,
        status: str,
        error: dict[str, Any] | None = None,
    ) -> None:
        now = utc_now().isoformat()
        thread_status = {
            "completed": "idle",
            "interrupted": "interrupted",
            "error": "error",
            "cancelled": "idle",
        }.get(status, "idle")
        with self.connect() as conn:
            self._execute(
                conn,
                """
                update rerai_runs
                set status = %s, error = %s, updated_at = %s, completed_at = %s
                where run_id = %s
                """,
                status,
                self._json(error),
                now,
                now,
                run_id,
            )
            self._execute(
                conn,
                "update rerai_threads set status = %s, updated_at = %s where thread_id = %s and deleted_at is null",
                thread_status,
                now,
                thread_id,
            )

    def append_run_event(
        self,
        *,
        run_id: str,
        thread_id: str,
        event: str,
        data: Any,
    ) -> int:
        now = utc_now().isoformat()
        with self.connect() as conn:
            row = self._fetchone(
                conn,
                "select coalesce(max(stream_id), 0) + 1 as next_stream_id from rerai_run_events where run_id = %s",
                run_id,
            )
            stream_id = int(
                row["next_stream_id"]
                if self.backend == "postgres"
                else row["next_stream_id"]
            )
            self._execute(
                conn,
                """
                insert into rerai_run_events (run_id, thread_id, stream_id, event, data, created_at)
                values (%s, %s, %s, %s, %s, %s)
                """,
                run_id,
                thread_id,
                stream_id,
                event,
                self._json(data),
                now,
            )
            return stream_id

    def list_run_events(
        self, run_id: str, *, after_id: int = 0
    ) -> list[RunEventRecord]:
        with self.connect() as conn:
            cursor = self._execute(
                conn,
                """
                select run_id, thread_id, stream_id, event, data, created_at
                from rerai_run_events
                where run_id = %s and stream_id > %s
                order by stream_id asc
                """,
                run_id,
                after_id,
            )
            rows = cursor.fetchall()
        return [self._row_to_event(row) for row in rows]

    def _fetch_thread(
        self, conn, thread_id: str, *, include_deleted: bool
    ) -> ThreadRecord | None:
        sql = "select * from rerai_threads where thread_id = %s"
        params: list[Any] = [thread_id]
        if not include_deleted:
            sql += " and deleted_at is null"
        row = self._fetchone(conn, sql, *params)
        if row is None:
            return None
        return self._row_to_thread(row)

    def _row_to_thread(self, row: Any) -> ThreadRecord:
        return ThreadRecord(
            thread_id=str(row["thread_id"]),
            metadata=self._json_read(row["metadata"], fallback={}),
            status=row["status"],
            created_at=self._coerce_datetime(row["created_at"]),
            updated_at=self._coerce_datetime(row["updated_at"]),
            deleted_at=self._coerce_datetime(row["deleted_at"])
            if row["deleted_at"]
            else None,
        )

    def _row_to_run(self, row: Any) -> RunRecord:
        return RunRecord(
            run_id=str(row["run_id"]),
            thread_id=str(row["thread_id"]),
            assistant_id=row["assistant_id"],
            status=row["status"],
            metadata=self._json_read(row["metadata"], fallback={}),
            config=self._json_read(row["config"], fallback=None),
            context=self._json_read(row["context"], fallback=None),
            input_payload=self._json_read(row["input_payload"], fallback=None),
            command_payload=self._json_read(row["command_payload"], fallback=None),
            stream_mode=self._json_read(row["stream_mode"], fallback=[]),
            on_disconnect=row["on_disconnect"],
            created_at=self._coerce_datetime(row["created_at"]),
            updated_at=self._coerce_datetime(row["updated_at"]),
            completed_at=self._coerce_datetime(row["completed_at"])
            if row["completed_at"]
            else None,
            error=self._json_read(row["error"], fallback=None),
        )

    def _row_to_event(self, row: Any) -> RunEventRecord:
        return RunEventRecord(
            run_id=str(row["run_id"]),
            thread_id=str(row["thread_id"]),
            stream_id=int(row["stream_id"]),
            event=row["event"],
            data=self._json_read(row["data"], fallback=None),
            created_at=self._coerce_datetime(row["created_at"]),
        )

    def _execute(self, conn, sql: str, *params: Any):
        query = sql.replace("%s", "?") if self.backend == "sqlite" else sql
        cursor = conn.cursor()
        cursor.execute(query, params)
        return cursor

    def _fetchone(self, conn, sql: str, *params: Any):
        cursor = self._execute(conn, sql, *params)
        row = cursor.fetchone()
        if row is None:
            return None
        if self.backend == "sqlite":
            return dict(row)
        return row

    def _json(self, value: Any) -> Any:
        if self.backend == "postgres":
            return json_dumps(value) if value is not None else None
        return json_dumps(value) if value is not None else None

    def _json_read(self, value: Any, *, fallback: Any) -> Any:
        if value is None:
            return fallback
        if isinstance(value, (dict, list)):
            return value
        return json_loads(value, fallback)

    def _coerce_datetime(self, value: Any) -> str:
        if isinstance(value, datetime):
            return value.astimezone(UTC).isoformat()
        return str(value)
