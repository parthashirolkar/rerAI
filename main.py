import asyncio
import json
import uuid
from pathlib import Path

import aiosqlite
from dotenv import load_dotenv
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

load_dotenv()

from deepagents import create_deep_agent  # noqa: E402

from subagents.definitions import ALL_SUBAGENTS  # noqa: E402
from tools.config import get_chat_model  # noqa: E402
from tools.gis_tools import (  # noqa: E402
    check_development_plan,
    query_pmrda_layer,
)
from tools.land_records_tools import (  # noqa: E402
    fetch_7_12_extract,
    fetch_property_card,
)
from tools.rera_tools import (  # noqa: E402
    get_rera_project_details,
    search_rera_projects,
)
from tools.regulatory_tools import init_udcpr_store, query_udcpr  # noqa: E402
from tools.transit_tools import check_transit_proximity  # noqa: E402

SYSTEM_PROMPT = """\
<role>
You are rerAI, an autonomous permitting assistant for Pune, Maharashtra, India.
</role>

<goal>
Given a plot query (address, survey/gat number, or coordinates), produce a structured permit
feasibility report by orchestrating specialized subagents to gather and analyze regulatory,
spatial, and title data.
</goal>

<subagents>
- rera-analyst: Search MahaRERA registered projects by district, fetch project details,
  check developer compliance history and registration status.
- regulatory-checker: Query UDCPR building regulations via semantic search — FSI limits,
  setbacks, parking norms, fire safety, height restrictions, ground coverage, zoning rules.
- gis-analyst: Analyze spatial context — transit proximity (metro, railway, bus), PMRDA
  jurisdiction boundaries, development plan zones, building permissions, environmental overlays.
- title-verifier: Verify land title and ownership from Mahabhulekh 7/12 extracts and
  property cards — owners, classification, encumbrances, area discrepancies.
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
- Note that GIS and land records data are for preliminary screening only — not for
  legal or regulatory decisions.
- Use Markdown for structure: headers, tables, and bullet lists.
</output_standards>
"""

ALL_TOOLS = [
    search_rera_projects,
    get_rera_project_details,
    query_udcpr,
    check_transit_proximity,
    query_pmrda_layer,
    check_development_plan,
    fetch_7_12_extract,
    fetch_property_card,
]


def _prompt_decision(action_request: dict) -> dict:
    name = action_request["name"]
    args = action_request.get("args", {})
    print(f"\n  Tool: {name}")
    print(f"  Args: {json.dumps(args, indent=4, default=str)}")

    while True:
        choice = input("  [a]pprove / [r]eject: ").strip().lower()
        if choice in ("a", "approve"):
            return {"type": "approve"}
        if choice in ("r", "reject"):
            while True:
                reason = input("  Reason (required): ").strip()
                if reason:
                    return {"type": "reject", "message": reason}
                print("  Reject requires a reason. Please provide one.")
        print("  Invalid choice. Enter a or r.")


async def main():
    print("Initializing UDCPR vector store...")
    chunk_count = init_udcpr_store()
    print(f"UDCPR store ready: {chunk_count} chunks")

    model = get_chat_model()

    db_path = Path.home() / ".config" / "rerAI" / "rerai.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(str(db_path)) as conn:
        checkpointer = AsyncSqliteSaver(conn)

        interrupt_on = {t.name: True for t in ALL_TOOLS}

        agent = create_deep_agent(
            model=model,
            tools=ALL_TOOLS,
            subagents=ALL_SUBAGENTS,
            memory=["./memory/AGENT_KNOWLEDGE.md"],
            skills=["./skills/"],
            system_prompt=SYSTEM_PROMPT,
            checkpointer=checkpointer,
            interrupt_on=interrupt_on,
        )

        thread_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}

        print(f"\nrerAI ready. Session: {thread_id[:8]}...")
        print("Type your query (or 'quit' to exit):\n")

        while True:
            try:
                user_input = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye!")
                break

            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit", "q"):
                print("Goodbye!")
                break

            result = await agent.ainvoke(
                {"messages": [{"role": "user", "content": user_input}]},
                config,
                version="v2",
            )

            while result.interrupts:
                resume = {}
                for interrupt in result.interrupts:
                    action_requests = interrupt.value["action_requests"]
                    print(
                        f"\n--- HITL: {len(action_requests)} tool call(s) pending "
                        f"(interrupt {interrupt.id[:8]}) ---"
                    )
                    decisions = []
                    for i, ar in enumerate(action_requests, 1):
                        print(f"\n  [{i}/{len(action_requests)}]")
                        decisions.append(_prompt_decision(ar))
                    resume[interrupt.id] = {"decisions": decisions}

                result = await agent.ainvoke(
                    Command(resume=resume),
                    config,
                    version="v2",
                )

            last_msg = result.value["messages"][-1]
            print(f"\nrerAI: {last_msg.content}\n")


if __name__ == "__main__":
    asyncio.run(main())
