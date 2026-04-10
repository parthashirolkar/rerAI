# AGENTS.md — rerAI

AI agent guidelines for the rerAI codebase — an autonomous permitting assistant for Pune, Maharashtra using the `deepagents` framework.

## Build & Development Commands

```bash
# Setup (using uv - the project package manager)
uv sync                    # Install all dependencies + dev dependencies
uv sync --no-dev          # Install production dependencies only

# Linting & Formatting (Ruff)
uv run ruff check .        # Check all files for lint errors
uv run ruff check --fix .  # Auto-fix lint errors
uv run ruff format .       # Format all files

# Running Tests
uv run pytest                              # All tests (including live API tests)
uv run pytest -m "not live"                # Unit tests only (no network)
uv run pytest tests/test_integration.py -m live  # Integration chain tests only
```

## Code Style Guidelines

### Python Standards
- **Python version**: 3.13+
- **Formatter/Linter**: Ruff (configured in pyproject.toml if present)
- **Quotes**: Use double quotes `"` for strings


## Skill Format

Skills are markdown files in `skills/<name>/SKILL.md` with frontmatter:

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

## Key Dependencies

- `deepagents`: Agent orchestration framework
- `langchain-*`: LLM tools and embeddings
- `chromadb`: Vector store for regulations
- `pypdf`: PDF text extraction
- `beautifulsoup4`: HTML parsing for RERA scraping
- `playwright`: Browser automation (planned)
