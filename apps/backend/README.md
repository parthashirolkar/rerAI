# rerAI backend

This app hosts the rerAI deepagents graph as a standalone LangGraph API server.

It is a Python app managed with `uv` (`pyproject.toml` + `uv.lock`) and does not
participate in Bun workspace package linking.

## Local development

1. Install dependencies:

```bash
uv sync
```

2. Copy the backend env template to the repo root and fill secrets:

```bash
cp .env.example ../../.env
```

3. Start LangGraph API server:

```bash
uv run langgraph dev
```

The API will expose endpoints like `/threads`, `/runs`, and `/threads/{id}/runs/stream`.

## Docker image build

Build image:

```bash
uv run langgraph build -t rerai-langgraph-api
```

Run image:

```bash
docker run --rm -p 8123:8000 --env-file ../../.env rerai-langgraph-api
```

Health check:

```bash
curl http://localhost:8123/ok
```

## Persistence env vars

Use these variables in Railway (or any Docker host):

- `DATABASE_URI`: Postgres for assistants/threads/runs/checkpoints/store.
- `LANGGRAPH_SETUP_DB`: If `true`, runs `store.setup()` and `checkpointer.setup()` at startup.
- `REDIS_URI`: Redis pub-sub for streaming and background jobs.
- `LANGGRAPH_POSTGRES_POOL_MAX_SIZE`: Tune connections for free-tier DB limits.
- `N_JOBS_PER_WORKER`: Controls background worker concurrency.
- `BG_JOB_ISOLATED_LOOPS`: Recommended for graphs with blocking code.

In addition, configure application env vars used by tools:

- `OPENROUTER_API_KEY`
- `CHROMA_API_KEY`
- `CHROMA_TENANT`
- `CHROMA_DATABASE`
- `MAHARERA_PUBLIC_USERNAME` (optional)
- `MAHARERA_PUBLIC_PASSWORD` (optional)
- `MAHARERA_CRYPTOJS_KEY` (optional)
- `UDCPR_PDF_DIR` (optional)

If you set `UDCPR_PDF_DIR`, use a path relative to `apps/backend` (for example,
`../../data/pdfs`) or an absolute path.

The exported graph (`rerai_agent.graph:graph`) reads `DATABASE_URI` at import time.
When present, it wires both `PostgresSaver` and `PostgresStore` into `create_deep_agent(...)`
so conversations/checkpoints are persisted automatically in the Dockerized LangGraph server.
