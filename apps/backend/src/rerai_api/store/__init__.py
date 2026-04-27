from __future__ import annotations

from datetime import UTC, datetime

from ._records import RunEventRecord, RunRecord, ThreadRecord
from ._store import Store


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


__all__ = [
    "Store",
    "ThreadRecord",
    "RunRecord",
    "RunEventRecord",
    "utc_now",
]
