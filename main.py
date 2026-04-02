from dotenv import load_dotenv

load_dotenv()

from deepagents import create_deep_agent  # noqa: E402

from subagents.definitions import ALL_SUBAGENTS  # noqa: E402
from tools.config import get_chat_model  # noqa: E402
from tools.rera_tools import (  # noqa: E402
    get_rera_project_details,
    search_rera_projects,
)
from tools.regulatory_tools import init_udcpr_store, query_udcpr  # noqa: E402

SYSTEM_PROMPT = """\
You are rerAI, an autonomous permitting assistant for Pune, Maharashtra, India.

Given a plot query (address, survey/gat number, or coordinates), you:
1. Plan the assessment via write_todos
2. Delegate to subagents for parallel data gathering
3. Synthesize findings into a structured permit feasibility report

Available subagents:
- rera-analyst: Search MahaRERA projects by district, check developer compliance
- regulatory-checker: Query UDCPR building regulations (FSI, setbacks, parking, fire norms)

Always cite regulation clause numbers and page references.
State assumptions clearly when data is incomplete.
"""


def main():
    print("Initializing UDCPR vector store...")
    chunk_count = init_udcpr_store()
    print(f"UDCPR store ready: {chunk_count} chunks")

    model = get_chat_model()

    agent = create_deep_agent(
        model=model,
        tools=[search_rera_projects, get_rera_project_details, query_udcpr],
        subagents=ALL_SUBAGENTS,
        memory=["./memory/AGENT_KNOWLEDGE.md"],
        skills=["./skills/"],
        system_prompt=SYSTEM_PROMPT,
    )

    print("\nrerAI ready. Type your query (or 'quit' to exit):\n")

    messages = []
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

        messages.append({"role": "user", "content": user_input})

        result = agent.invoke({"messages": messages})

        assistant_msg = result["messages"][-1]
        print(f"\nrerAI: {assistant_msg.content}\n")

        messages = result["messages"]


if __name__ == "__main__":
    main()
