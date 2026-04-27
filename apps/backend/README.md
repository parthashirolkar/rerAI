# rerAI backend

This app hosts the rerAI deepagents graph behind a native FastAPI service that mimics the LangGraph thread/run surface the current web app uses directly.

The backend keeps:
- the existing `rerai_agent.graph` graph
- LangGraph checkpoint/store persistence
- direct browser-to-backend SDK usage with Convex bearer-token auth

It replaces:
- the hosted/self-hosted Agent Server dependency

## Local development

1. Install dependencies:

```bash
/home/partha/.local/bin/uv sync
```

2. Copy the backend env template to the repo root and fill secrets:

```bash
cp .env.example ../../.env
```

3. Start the FastAPI backend:

```bash
/home/partha/.local/bin/uv run uvicorn app:app --reload --host 127.0.0.1 --port 8123
```

The service exposes the subset of endpoints the current app needs, including:
- `/ok`
- `/info`
- `/assistants/{assistant_id}`
- `/threads`
- `/threads/{thread_id}/state`
- `/threads/{thread_id}/history`
- `/threads/{thread_id}/runs/stream`
- `/threads/{thread_id}/runs/{run_id}/stream`

All routes except `/ok` require `Authorization: Bearer <Convex auth token>`.
The backend validates the token and verifies thread ownership through Convex.

## Persistence

`DATABASE_URI` is the single persistence setting for:
- LangGraph checkpoints/store
- rerAI thread metadata
- rerAI run metadata
- persisted SSE replay events

Supported values:
- SQLite for local dev, for example `sqlite:///tmp/rerai-backend.db`
- Postgres for Railway/Supabase, for example `postgresql://...`

If `LANGGRAPH_SETUP_DB=true`, startup creates:
- LangGraph checkpoint/store tables
- `rerai_threads`
- `rerai_runs`
- `rerai_run_events`

Redis is intentionally not used in MVP1. Streaming fanout is handled in-process and is only safe for a single Railway replica.

## Railway deployment

Use a dedicated Railway service with root directory set to `apps/backend`.

This repo includes:
- `apps/backend/Dockerfile`: builds the FastAPI backend directly
- `apps/backend/railway.json`: Dockerfile deploys, `/ok` health checks, restart policy

The Dockerfile binds Uvicorn to `0.0.0.0:${PORT:-8000}` so the same image works both:
- on Railway, where `PORT` is injected at runtime
- locally, where it falls back to `8000`

Recommended setup:

1. Create a new Railway service for `apps/backend`.
2. Set the root directory to `apps/backend`.
3. Expose the backend to the frontend origin.
4. Set `DATABASE_URI` to a Supabase or Railway Postgres connection string.
5. Set `CONVEX_URL` to the Convex deployment URL used by `/api/query` and `/api/mutation`.
6. Keep `LANGGRAPH_SETUP_DB=true` on the first deploy.
7. Set `CLIENT_ORIGINS` to the deployed web origin.
8. Deploy from GitHub.

Notes:
- Railway injects the runtime port, so the backend container must not assume `8000` is the actual listening port in production.
- The frontend sends Convex auth tokens to the backend for LangGraph calls.

## Supabase Postgres

Supabase works as the production backing store because the backend only needs a standard Postgres connection string.

Recommended setup:
- use the direct Postgres connection string when available
- include `sslmode=require` if needed
- keep the service single-replica until Redis-backed fanout exists

Convex still stores application-facing chat metadata and auth state. This backend stores runtime thread/run state and resumable event replay data.
