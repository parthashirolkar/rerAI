from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Protocol

import psycopg
from psycopg.rows import dict_row

from ._dialect import _Dialect


def _is_postgres_uri(value: str) -> bool:
    lowered = value.strip().lower()
    return lowered.startswith("postgresql://") or lowered.startswith("postgres://")


def _is_sqlite_uri(value: str) -> bool:
    return value.strip().lower().startswith("sqlite://")


def _sqlite_path(value: str) -> str:
    if not _is_sqlite_uri(value):
        return value
    path = value[len("sqlite://") :]
    if path.startswith("/"):
        return path
    return str((Path.cwd() / path).resolve())


class _Engine(Protocol):
    @contextmanager
    def connect(self) -> Iterator[Any]: ...

    def execute(self, conn: Any, sql: str, *params: Any) -> Any: ...

    def fetchone(self, conn: Any, sql: str, *params: Any) -> dict[str, Any] | None: ...

    def fetchall(self, conn: Any, sql: str, *params: Any) -> list[dict[str, Any]]: ...


class _BaseEngine:
    def __init__(self, dialect: _Dialect) -> None:
        self._dialect = dialect

    def _rewrite(self, sql: str) -> str:
        return sql.replace("%s", self._dialect.placeholder)

    def execute(self, conn: Any, sql: str, *params: Any) -> Any:
        cursor = conn.cursor()
        cursor.execute(self._rewrite(sql), params)
        return cursor

    def fetchone(self, conn: Any, sql: str, *params: Any) -> dict[str, Any] | None:
        cursor = self.execute(conn, sql, *params)
        row = cursor.fetchone()
        if row is None:
            return None
        return self._dialect.adapt_row(row)

    def fetchall(self, conn: Any, sql: str, *params: Any) -> list[dict[str, Any]]:
        cursor = self.execute(conn, sql, *params)
        rows = cursor.fetchall()
        return [self._dialect.adapt_row(row) for row in rows]


class _PsycopgEngine(_BaseEngine):
    def __init__(self, database_uri: str, dialect: _Dialect) -> None:
        super().__init__(dialect)
        self._database_uri = database_uri

    @contextmanager
    def connect(self) -> Iterator[Any]:
        conn = psycopg.connect(self._database_uri, row_factory=dict_row)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


class _SqliteEngine(_BaseEngine):
    def __init__(self, database_uri: str, dialect: _Dialect) -> None:
        super().__init__(dialect)
        self._raw_uri = database_uri
        self._is_file_uri = database_uri.lower().startswith("file:")
        self._path = database_uri if self._is_file_uri else _sqlite_path(database_uri)

    @contextmanager
    def connect(self) -> Iterator[Any]:
        if self._is_file_uri:
            conn = sqlite3.connect(self._path, uri=True, check_same_thread=False)
        else:
            path = Path(self._path)
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
