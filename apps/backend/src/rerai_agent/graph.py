import atexit
import asyncio
import os
from contextlib import AsyncExitStack, ExitStack
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.store.postgres import PostgresStore
from langgraph.store.postgres.aio import AsyncPostgresStore
from langgraph.store.sqlite import SqliteStore
from langgraph.store.sqlite.aio import AsyncSqliteStore

from rerai_agent.subagents.definitions import ALL_SUBAGENTS
from rerai_agent.tools.config import get_chat_model
from rerai_agent.tools.gis_tools import (
    check_development_plan,
    geocode_address,
    query_pmrda_layer,
)
from rerai_agent.tools.regulatory_tools import init_udcpr_store, query_udcpr
from rerai_agent.tools.rera_tools import (
    get_rera_project_details,
    search_rera_projects,
)
from rerai_agent.tools.transit_tools import check_transit_proximity

SYSTEM_PROMPT = """\
<role>
You are rerAI, an autonomous permitting assistant for Pune, Maharashtra, India.
</role>

<goal>
Given a plot query (address, survey/gat number, or coordinates), produce a structured permit
feasibility report by orchestrating specialized subagents to gather and analyze regulatory
and spatial data.
</goal>

<subagents>
- rera-analyst: Search MahaRERA registered projects by district, fetch project details,
  check developer compliance history and registration status.
- regulatory-checker: Query UDCPR building regulations via semantic search — FSI limits,
  setbacks, parking norms, fire safety, height restrictions, ground coverage, zoning rules.
- gis-analyst: Analyze spatial context — transit proximity (metro, railway, bus), PMRDA
  jurisdiction boundaries, development plan zones, building permissions, environmental overlays.

</subagents>

<workflow>
1. Decompose the user's query into all required sub-tasks via write_todos.
2. Delegate independent sub-tasks to subagents in parallel to minimize latency.
3. Wait for all subagent results before synthesizing — do not produce the final report
   until every sub-task is resolved.
4. Synthesize all findings into a single structured permit feasibility report.
</workflow>

<persistence>
- You are an agent — keep going until the user's query is completely resolved before ending
  your turn. Only terminate when the full assessment is delivered.
- Do not stop or hand back to the user when you encounter missing data or uncertainty.
  Instead, state your assumptions clearly, proceed with the best available information,
  and document those assumptions in the report.
- When delegating to subagents, dispatch all independent tasks in parallel immediately.
</persistence>

<tool_preambles>
- Before delegating to a subagent, briefly state what you expect it to find and why.
- After receiving subagent results, summarize the key takeaway in one sentence before
  moving to the next step.
</tool_preambles>

<output_standards>
- Always cite regulation clause numbers and page references from UDCPR.
- State assumptions clearly when data is incomplete.
- Note that GIS data is for preliminary screening only — not for
  legal or regulatory decisions.
- Use Markdown for structure: headers, tables, and bullet lists.
</output_standards>
"""

ALL_TOOLS = [
    search_rera_projects,
    get_rera_project_details,
    query_udcpr,
    geocode_address,
    check_transit_proximity,
    query_pmrda_layer,
    check_development_plan,
]

_udcpr_store_initialized = False


def initialize_udcpr_store() -> int:
    global _udcpr_store_initialized
    if not _udcpr_store_initialized:
        chunk_count = init_udcpr_store()
        _udcpr_store_initialized = True
        return chunk_count
    return 0


BASE_DIR = Path(__file__).resolve().parent
MEMORY_FILE = BASE_DIR / "memory" / "AGENT_KNOWLEDGE.md"
SKILLS_DIR = BASE_DIR / "skills"

_persistence_stack: ExitStack | None = None
_checkpointer: PostgresSaver | SqliteSaver | None = None
_store: PostgresStore | SqliteStore | None = None
_async_persistence_stack: AsyncExitStack | None = None
_async_checkpointer: AsyncPostgresSaver | AsyncSqliteSaver | None = None
_async_store: AsyncPostgresStore | AsyncSqliteStore | None = None


def _env_enabled(name: str, default: str = "true") -> bool:
    value = os.getenv(name, default).strip().lower()
    return value in {"1", "true", "yes", "on"}


def _is_postgres_uri(value: str) -> bool:
    value = value.strip().lower()
    return value.startswith("postgresql://") or value.startswith("postgres://")


def _is_sqlite_uri(value: str) -> bool:
    return value.strip().lower().startswith("sqlite://")


def _sqlite_conn_string(value: str) -> str:
    return value[len("sqlite://") :]


def _init_persistence(
    database_uri: str | None = None,
) -> tuple[PostgresSaver | SqliteSaver | None, PostgresStore | SqliteStore | None]:
    global _persistence_stack, _checkpointer, _store

    if _checkpointer is not None or _store is not None:
        return _checkpointer, _store

    database_uri = (database_uri or os.getenv("DATABASE_URI", "")).strip()
    if not database_uri:
        return None, None
    if _is_sqlite_uri(database_uri):
        return None, None

    stack = ExitStack()
    try:
        if _is_postgres_uri(database_uri):
            store = stack.enter_context(PostgresStore.from_conn_string(database_uri))
            checkpointer = stack.enter_context(
                PostgresSaver.from_conn_string(database_uri)
            )
        elif _is_sqlite_uri(database_uri):
            conn_string = _sqlite_conn_string(database_uri)
            store = stack.enter_context(SqliteStore.from_conn_string(conn_string))
            checkpointer = stack.enter_context(
                SqliteSaver.from_conn_string(conn_string)
            )
        else:
            return None, None

        if _env_enabled("LANGGRAPH_SETUP_DB", default="true"):
            store.setup()
            checkpointer.setup()

        _persistence_stack = stack
        _store = store
        _checkpointer = checkpointer
        return _checkpointer, _store
    except Exception:
        stack.close()
        raise


async def _ainit_persistence(
    database_uri: str | None = None,
) -> tuple[
    AsyncPostgresSaver | AsyncSqliteSaver | None,
    AsyncPostgresStore | AsyncSqliteStore | None,
]:
    global _async_persistence_stack, _async_checkpointer, _async_store

    database_uri = (database_uri or os.getenv("DATABASE_URI", "")).strip()
    if not database_uri:
        return None, None

    if _async_checkpointer is not None or _async_store is not None:
        return _async_checkpointer, _async_store

    stack = AsyncExitStack()
    try:
        if _is_sqlite_uri(database_uri):
            conn_string = _sqlite_conn_string(database_uri)
            store = await stack.enter_async_context(
                AsyncSqliteStore.from_conn_string(conn_string)
            )
            checkpointer = await stack.enter_async_context(
                AsyncSqliteSaver.from_conn_string(conn_string)
            )
        elif _is_postgres_uri(database_uri):
            store = await stack.enter_async_context(
                AsyncPostgresStore.from_conn_string(database_uri)
            )
            checkpointer = await stack.enter_async_context(
                AsyncPostgresSaver.from_conn_string(database_uri)
            )
        else:
            await stack.aclose()
            return None, None

        if _env_enabled("LANGGRAPH_SETUP_DB", default="true"):
            await store.setup()
            await checkpointer.setup()

        _async_persistence_stack = stack
        _async_store = store
        _async_checkpointer = checkpointer
        return _async_checkpointer, _async_store
    except Exception:
        await stack.aclose()
        raise


def _close_persistence() -> None:
    global _persistence_stack
    if _persistence_stack is not None:
        _persistence_stack.close()
        _persistence_stack = None

    global _async_persistence_stack
    if _async_persistence_stack is not None:
        try:
            asyncio.run(_async_persistence_stack.aclose())
        except Exception:
            pass
        _async_persistence_stack = None


atexit.register(_close_persistence)


def build_graph(checkpointer=None, store=None, backend=None, interrupt_on=None):
    return create_deep_agent(
        model=get_chat_model(),
        tools=ALL_TOOLS,
        subagents=ALL_SUBAGENTS,
        memory=[str(MEMORY_FILE)],
        skills=[str(SKILLS_DIR)],
        system_prompt=SYSTEM_PROMPT,
        checkpointer=checkpointer,
        store=store,
        backend=backend or (lambda runtime: StateBackend(runtime)),
        interrupt_on=interrupt_on,
    )


def build_persisted_graph(
    *,
    database_uri: str | None = None,
    backend=None,
    interrupt_on=None,
):
    checkpointer, store = _init_persistence(database_uri)
    return build_graph(
        checkpointer=checkpointer,
        store=store,
        backend=backend,
        interrupt_on=interrupt_on,
    )


async def build_persisted_graph_async(
    *,
    database_uri: str | None = None,
    backend=None,
    interrupt_on=None,
):
    checkpointer, store = await _ainit_persistence(database_uri)
    return build_graph(
        checkpointer=checkpointer,
        store=store,
        backend=backend,
        interrupt_on=interrupt_on,
    )


graph = build_persisted_graph()
