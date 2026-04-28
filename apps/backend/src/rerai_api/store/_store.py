from __future__ import annotations

import contextlib
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, Iterator, Literal
from uuid import uuid4

from ._dialect import _Dialect, _PostgresDialect, _SqliteDialect
from ._engine import _Engine, _is_postgres_uri, _PsycopgEngine, _SqliteEngine
from ._records import RunEventRecord, RunRecord, ThreadRecord


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


class Store:
    def __init__(self, database_uri: str) -> None:
        self._database_uri = database_uri.strip()
        if _is_postgres_uri(self._database_uri):
            self._dialect: _Dialect = _PostgresDialect()
            self._engine: _Engine = _PsycopgEngine(self._database_uri, self._dialect)
        else:
            self._dialect = _SqliteDialect()
            self._engine = _SqliteEngine(self._database_uri, self._dialect)
        self._in_transaction = False
        self._tx_conn: Any = None

    @classmethod
    def memory(cls) -> Store:
        """Fast in-memory SQLite. Zero external dependencies."""
        name = uuid4().hex
        return cls(f"file:{name}?mode=memory&cache=shared")

    def setup(self) -> None:
        with self._connect() as conn:
            for sql in self._dialect.setup_statements():
                self._engine.execute(conn, sql)

    @contextmanager
    def transaction(self) -> Iterator[Store]:
        if self._in_transaction:
            yield self
            return
        with self._engine.connect() as conn:
            self._tx_conn = conn
            self._in_transaction = True
            try:
                yield self
            finally:
                self._in_transaction = False
                self._tx_conn = None

    # ------------------------------------------------------------------
    # Threads
    # ------------------------------------------------------------------
    def create_thread(
        self,
        thread_id: str | None = None,
        *,
        metadata: dict | None = None,
        if_exists: Literal["raise", "do_nothing"] = "raise",
    ) -> ThreadRecord:
        metadata = metadata or {}
        thread_id = thread_id or str(uuid4())
        now = _utc_now().isoformat()
        with self._connect() as conn:
            existing = self._fetch_thread(conn, thread_id, include_deleted=True)
            if existing and existing.deleted_at is None:
                if if_exists == "do_nothing":
                    return existing
                raise ValueError(f"Thread {thread_id} already exists")
            if existing and existing.deleted_at is not None:
                self._engine.execute(
                    conn,
                    """
                    update rerai_threads
                    set metadata = %s, status = %s, created_at = %s, updated_at = %s, deleted_at = null
                    where thread_id = %s
                    """,
                    self._dialect.adapt_json(metadata),
                    "idle",
                    now,
                    now,
                    thread_id,
                )
            else:
                self._engine.execute(
                    conn,
                    """
                    insert into rerai_threads (thread_id, metadata, status, created_at, updated_at)
                    values (%s, %s, %s, %s, %s)
                    """,
                    thread_id,
                    self._dialect.adapt_json(metadata),
                    "idle",
                    now,
                    now,
                )
            return self._fetch_thread(conn, thread_id, include_deleted=True)

    def get_thread(self, thread_id: str) -> ThreadRecord | None:
        with self._connect() as conn:
            return self._fetch_thread(conn, thread_id, include_deleted=False)

    def delete_thread(self, thread_id: str) -> bool:
        now = _utc_now().isoformat()
        with self._connect() as conn:
            record = self._fetch_thread(conn, thread_id, include_deleted=False)
            if record is None:
                return False
            self._engine.execute(
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
            self._engine.execute(
                conn, "delete from rerai_run_events where thread_id = %s", thread_id
            )
            self._engine.execute(
                conn, "delete from rerai_runs where thread_id = %s", thread_id
            )
            return True

    def set_thread_status(self, thread_id: str, status: str) -> None:
        now = _utc_now().isoformat()
        with self._connect() as conn:
            self._engine.execute(
                conn,
                "update rerai_threads set status = %s, updated_at = %s where thread_id = %s and deleted_at is null",
                status,
                now,
                thread_id,
            )

    # ------------------------------------------------------------------
    # Runs
    # ------------------------------------------------------------------
    def create_run(
        self,
        *,
        thread_id: str,
        assistant_id: str = "rerai",
        input_payload: Any = None,
        config: dict | None = None,
        context: dict | None = None,
        command_payload: dict | None = None,
        metadata: dict | None = None,
        stream_mode: list[str] | None = None,
        on_disconnect: str = "continue",
        run_id: str | None = None,
    ) -> RunRecord:
        run_id = run_id or str(uuid4())
        metadata = metadata or {}
        stream_mode = stream_mode or ["values"]
        now = _utc_now().isoformat()
        with self._connect() as conn:
            self._engine.execute(
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
                self._dialect.adapt_json(metadata),
                self._dialect.adapt_json(config),
                self._dialect.adapt_json(context),
                self._dialect.adapt_json(input_payload),
                self._dialect.adapt_json(command_payload),
                self._dialect.adapt_json(stream_mode),
                on_disconnect,
                now,
                now,
            )
            self._engine.execute(
                conn,
                "update rerai_threads set status = %s, updated_at = %s where thread_id = %s and deleted_at is null",
                "busy",
                now,
                thread_id,
            )
            return self._fetch_run(conn, run_id)

    def get_run(self, run_id: str) -> RunRecord | None:
        with self._connect() as conn:
            return self._fetch_run(conn, run_id)

    def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        error: dict | None = None,
    ) -> None:
        now = _utc_now().isoformat()
        thread_status = {
            "completed": "idle",
            "interrupted": "interrupted",
            "error": "error",
            "cancelled": "idle",
        }.get(status, "idle")
        with self._connect() as conn:
            run = self._fetch_run(conn, run_id)
            if run is None:
                raise ValueError(f"Run {run_id} not found")
            thread_id = run.thread_id
            self._engine.execute(
                conn,
                """
                update rerai_runs
                set status = %s, error = %s, updated_at = %s, completed_at = %s
                where run_id = %s
                """,
                status,
                self._dialect.adapt_json(error),
                now,
                now,
                run_id,
            )
            self._engine.execute(
                conn,
                "update rerai_threads set status = %s, updated_at = %s where thread_id = %s and deleted_at is null",
                thread_status,
                now,
                thread_id,
            )

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    def append_event(
        self,
        run_id: str,
        event: str,
        data: Any,
        *,
        thread_id: str | None = None,
    ) -> int:
        now = _utc_now().isoformat()
        with self._connect() as conn:
            if thread_id is None:
                run = self._fetch_run(conn, run_id)
                if run is None:
                    raise ValueError(f"Run {run_id} not found")
                thread_id = run.thread_id
            row = self._engine.fetchone(
                conn,
                "select coalesce(max(stream_id), 0) + 1 as next_stream_id from rerai_run_events where run_id = %s",
                run_id,
            )
            stream_id = int(row["next_stream_id"])
            self._engine.execute(
                conn,
                """
                insert into rerai_run_events (run_id, thread_id, stream_id, event, data, created_at)
                values (%s, %s, %s, %s, %s, %s)
                """,
                run_id,
                thread_id,
                stream_id,
                event,
                self._dialect.adapt_json(data),
                now,
            )
            return stream_id

    def list_events(self, run_id: str, *, after: int = 0) -> list[RunEventRecord]:
        with self._connect() as conn:
            rows = self._engine.fetchall(
                conn,
                """
                select run_id, thread_id, stream_id, event, data, created_at
                from rerai_run_events
                where run_id = %s and stream_id > %s
                order by stream_id asc
                """,
                run_id,
                after,
            )
        return [self._row_to_event(row) for row in rows]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _connect(self):
        if self._in_transaction and self._tx_conn is not None:
            return contextlib.nullcontext(self._tx_conn)
        return self._engine.connect()

    def _fetch_thread(
        self, conn: Any, thread_id: str, *, include_deleted: bool
    ) -> ThreadRecord | None:
        sql = "select * from rerai_threads where thread_id = %s"
        params = [thread_id]
        if not include_deleted:
            sql += " and deleted_at is null"
        row = self._engine.fetchone(conn, sql, *params)
        if row is None:
            return None
        return self._row_to_thread(row)

    def _fetch_run(self, conn: Any, run_id: str) -> RunRecord | None:
        row = self._engine.fetchone(
            conn, "select * from rerai_runs where run_id = %s", run_id
        )
        if row is None:
            return None
        return self._row_to_run(row)

    def _row_to_thread(self, row: dict[str, Any]) -> ThreadRecord:
        return ThreadRecord(
            thread_id=str(row["thread_id"]),
            metadata=self._dialect.read_json(row["metadata"], fallback={}),
            status=row["status"],
            created_at=self._dialect.read_datetime(row["created_at"]),
            updated_at=self._dialect.read_datetime(row["updated_at"]),
            deleted_at=self._dialect.read_datetime(row["deleted_at"])
            if row.get("deleted_at")
            else None,
        )

    def _row_to_run(self, row: dict[str, Any]) -> RunRecord:
        return RunRecord(
            run_id=str(row["run_id"]),
            thread_id=str(row["thread_id"]),
            assistant_id=row["assistant_id"],
            status=row["status"],
            metadata=self._dialect.read_json(row["metadata"], fallback={}),
            config=self._dialect.read_json(row["config"], fallback=None),
            context=self._dialect.read_json(row["context"], fallback=None),
            input_payload=self._dialect.read_json(row["input_payload"], fallback=None),
            command_payload=self._dialect.read_json(
                row["command_payload"], fallback=None
            ),
            stream_mode=self._dialect.read_json(row["stream_mode"], fallback=[]),
            on_disconnect=row["on_disconnect"],
            created_at=self._dialect.read_datetime(row["created_at"]),
            updated_at=self._dialect.read_datetime(row["updated_at"]),
            completed_at=self._dialect.read_datetime(row["completed_at"])
            if row.get("completed_at")
            else None,
            error=self._dialect.read_json(row["error"], fallback=None),
        )

    def _row_to_event(self, row: dict[str, Any]) -> RunEventRecord:
        return RunEventRecord(
            run_id=str(row["run_id"]),
            thread_id=str(row["thread_id"]),
            stream_id=int(row["stream_id"]),
            event=row["event"],
            data=self._dialect.read_json(row["data"], fallback=None),
            created_at=self._dialect.read_datetime(row["created_at"]),
        )
