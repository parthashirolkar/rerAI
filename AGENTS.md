# AGENTS.md — rerAI

AI agent guidelines for the rerAI codebase — an autonomous permitting assistant for Pune, Maharashtra using the `deepagents` framework.

## Build & Development Commands

**Standing instruction:** Do not run build commands unless the user explicitly asks for that specific build command in the current turn.

```bash
# Root workspace
bun install
bun run dev
bun run test
bun run lint

# Backend
cd apps/backend && uv sync
cd apps/backend && uv run langgraph dev
cd apps/backend && uv run langgraph build -t rerai-langgraph-api

# Linting & Formatting (Ruff)
cd apps/backend && uv run ruff check .
cd apps/backend && uv run ruff check --fix .
cd apps/backend && uv run ruff format .

# Running Tests
cd apps/backend && OPENROUTER_API_KEY=dummy uv run pytest -m "not live"
```

## Code Style Guidelines

### Python Standards
- **Python version**: 3.13+
- **Formatter/Linter**: Ruff (configured in pyproject.toml if present)
- **Quotes**: Use double quotes `"` for strings


## Skill Format

Skills are markdown files in `apps/backend/src/rerai_agent/skills/<name>/SKILL.md` with frontmatter:

```yaml
---
name: skill-name
description: What this skill does
trigger: When to activate this skill
---
```

## Debugging Guidelines

- **Do NOT create test scripts** to debug tools or functions.
- Use the Bash tool to run inline Python directly: `uv run python -c "..."`
- Invoke tools via their async interface: `asyncio.run(tool.ainvoke({...}))`
- Check output length and content to verify fixes work as expected.

## Repo Layout

- `apps/backend`: Python agent runtime and LangGraph Docker backend
- `apps/web`: React frontend
- `apps/convex`: Convex app

## Key Dependencies

- `deepagents`: Agent orchestration framework
- `langchain-*`: LLM tools and embeddings
- `chromadb`: Vector store for regulations
- `pypdf`: PDF text extraction
- `beautifulsoup4`: HTML parsing for RERA scraping
- `playwright`: Browser automation (planned)
