# rerAI

rerAI is an autonomous permitting assistant for Pune, Maharashtra. This repo is a monorepo with a React frontend, a Convex app for auth and app state, and a Python backend that runs the rerAI graph behind a FastAPI service.

## Architecture

The request path is:

1. the rerAI frontend authenticates the user
2. the frontend calls the FastAPI backend directly for LangGraph-compatible thread/run traffic
3. the backend validates the Convex bearer token and checks thread ownership through Convex
4. the FastAPI backend runs the graph and returns a LangGraph-compatible SSE response

Important implication:
- the backend is the public agent API boundary
- Convex remains the identity and app-data source
- the backend requires `Authorization: Bearer <Convex auth token>` on every route except `/ok`

## Apps

- `apps/backend`: Python backend for the rerAI graph runtime, managed with `uv`
- `apps/web`: React + TypeScript + Vite frontend
- `apps/convex`: Convex app for auth, thread ownership, message persistence, and backend ownership checks

## Backend shape

The backend keeps the existing `rerai_agent.graph` graph and exposes the subset of the LangGraph thread/run API that the current app already uses.

Current MVP backend behavior:
- FastAPI service, not `langgraph dev`
- LangGraph-compatible endpoints for assistants, threads, state/history, and streaming runs
- LangGraph checkpoint/store persistence via `DATABASE_URI`
- rerAI-owned metadata tables for threads, runs, and resumable SSE replay
- single-process in-memory streaming fanout for MVP1

Current limitations:
- no Redis-backed multi-replica streaming yet
- no full Agent Server parity
- backend-side auth is still trust-based behind Convex/private networking

## Local development

### Prerequisites

- Bun
- Python 3.13
- `uv`

### Install

Workspace dependencies:

```bash
bun install
```

Backend dependencies:

```bash
cd apps/backend && /home/partha/.local/bin/uv sync
```

### Environment

Copy the backend env template to the repo root:

```bash
cp apps/backend/.env.example .env
```

Minimum backend variables:

- `DATABASE_URI`
- `OPENROUTER_API_KEY`
- `CHROMA_API_KEY`
- `CHROMA_TENANT`
- `CHROMA_DATABASE`

App-level variables also matter:

- the backend needs `CONVEX_URL` so it can validate users and thread ownership through Convex
- the backend needs `CLIENT_ORIGINS` for CORS
- the web app needs `VITE_CONVEX_URL` and `VITE_BACKEND_URL`

### Run everything

```bash
bun run dev
```

This starts:

- backend: `uv run uvicorn app:app --reload --host 127.0.0.1 --port 8123`
- web: Vite in `apps/web`
- convex: `convex dev` in `apps/convex`

You can also run them separately:

```bash
bun run backend:dev
bun run web:dev
bun run convex:dev
```

## Common commands

Backend dev server:

```bash
bun run backend:dev
```

Backend tests:

```bash
bun run backend:test
```

Backend lint:

```bash
bun run backend:lint
```

Frontend build:

```bash
bun run web:build
```

## Persistence

`DATABASE_URI` is the main backend persistence setting.

It is used for:

- LangGraph checkpoint/store persistence
- rerAI thread metadata
- rerAI run metadata
- persisted SSE replay events

Supported values:

- local SQLite, for example `sqlite:///tmp/rerai-backend.db`
- Postgres, including Supabase

If `LANGGRAPH_SETUP_DB=true`, startup will create both LangGraph tables and rerAI metadata tables.

## Deployment

### Backend

Deploy `apps/backend` as a dedicated Railway service using its Dockerfile.

Expected production pattern:

- frontend calls the backend directly for LangGraph/SSE traffic
- backend validates Convex bearer tokens and checks thread ownership through Convex
- Convex remains the identity and app-data service

### Web

Deploy `apps/web` to a static host. The recommended default is Cloudflare Pages.

Production web env vars:

- `VITE_CONVEX_URL`
- `VITE_BACKEND_URL`

The frontend does not need Google OAuth secrets or backend secrets. It only needs the public Convex URLs.

### Google OAuth

Google OAuth is handled by Convex Auth, not by the frontend host.

Set these on the Convex deployment:

- `AUTH_GOOGLE_ID`
- `AUTH_GOOGLE_SECRET`

The Google OAuth redirect URI must point at the Convex Site domain:

- `https://<your-convex-site>.convex.site/api/auth/callback/google`

### Convex

Deploy `apps/convex` with:

```bash
bun run convex:deploy
```

Production Convex env vars include:

- `AUTH_GOOGLE_ID`
- `AUTH_GOOGLE_SECRET`

## Repo notes

- The backend is managed by `uv`, not by Bun workspaces.
- The frontend calls the backend directly for LangGraph-compatible traffic.
- The backend preserves the existing LangGraph-compatible API surface needed by the app, but it no longer depends on hosted Agent Server infrastructure.

## More detail

- backend runtime and deployment details: [apps/backend/README.md](/home/partha/git-repos/rerAI/apps/backend/README.md)
- backend-facing Convex auth/thread checks: [apps/convex/convex/backend.ts](/home/partha/git-repos/rerAI/apps/convex/convex/backend.ts)
