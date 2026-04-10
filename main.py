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

from agent import ALL_SUBAGENTS, ALL_TOOLS, SYSTEM_PROMPT, initialize_udcpr_store  # noqa: E402
from tools.config import get_chat_model  # noqa: E402


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
    chunk_count = initialize_udcpr_store()
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
