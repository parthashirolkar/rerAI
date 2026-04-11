# rerAI monorepo

rerAI is an autonomous permitting assistant for Pune, Maharashtra.

## Layout

- `apps/backend`: Python/LangGraph backend (managed by `uv`, not Bun workspaces)
- `apps/web`: React + TypeScript + Vite + Tailwind frontend
- `apps/convex`: Convex app for UI/session state

## Monorepo rules

- Deployable apps live in `apps/`.
- Bun workspaces are declared as `apps/*`.
- The Python backend is intentionally not a JS workspace package; it is managed via `apps/backend/pyproject.toml` and `uv.lock`.
- Use the repo-root `.env`; app-local `.env` files are not required.

## Local development

1. Install workspace dependencies:

```bash
bun install
```

2. Install backend Python deps:

```bash
cd apps/backend && uv sync
```

3. Start everything:

```bash
bun run dev
```

This runs:
- backend: `uv run langgraph dev` in `apps/backend`
- web: Vite in `apps/web`
- convex: `convex dev` in `apps/convex`

Convex may prompt you to create/link a project the first time you run it.

If you want to run them separately:

```bash
bun run backend:dev
bun run web:dev
bun run convex:dev
```

## Backend env

Copy `apps/backend/.env.example` to `.env` at the repo root and set:

- `DATABASE_URI`
- `REDIS_URI`
- `OPENROUTER_API_KEY`
- `CHROMA_API_KEY`
- `CHROMA_TENANT`
- `CHROMA_DATABASE`

Frontend-only env vars (for Vite) can stay in `apps/web/.env.local`.

## Testing

```bash
bun run backend:test
bun run backend:lint
bun run web:build
```

## Deployment

- `apps/backend`: `bun run backend:build`, then deploy the Docker image to Railway or any Docker host
- `apps/web`: deploy to Vercel or Cloudflare Pages
- `apps/convex`: `bun run convex:deploy`

## Notes

- The backend is self-hosted LangGraph, not LangSmith.
