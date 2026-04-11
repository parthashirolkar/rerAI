import atexit
import os
from contextlib import ExitStack
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.store.postgres import PostgresStore

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
_checkpointer: PostgresSaver | None = None
_store: PostgresStore | None = None


def _env_enabled(name: str, default: str = "true") -> bool:
    value = os.getenv(name, default).strip().lower()
    return value in {"1", "true", "yes", "on"}


def _is_postgres_uri(value: str) -> bool:
    value = value.strip().lower()
    return value.startswith("postgresql://") or value.startswith("postgres://")


def _init_persistence() -> tuple[PostgresSaver | None, PostgresStore | None]:
    global _persistence_stack, _checkpointer, _store

    if _checkpointer is not None or _store is not None:
        return _checkpointer, _store

    database_uri = os.getenv("DATABASE_URI", "").strip()
    if not database_uri or not _is_postgres_uri(database_uri):
        return None, None

    stack = ExitStack()
    try:
        store = stack.enter_context(PostgresStore.from_conn_string(database_uri))
        checkpointer = stack.enter_context(PostgresSaver.from_conn_string(database_uri))

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


def _close_persistence() -> None:
    global _persistence_stack
    if _persistence_stack is not None:
        _persistence_stack.close()
        _persistence_stack = None


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


_default_checkpointer, _default_store = _init_persistence()

graph = build_graph(
    checkpointer=_default_checkpointer,
    store=_default_store,
    interrupt_on={t.name: True for t in ALL_TOOLS},
)
