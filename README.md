# rerAI — Autonomous Permitting Assistant

An AI-powered permitting agent for Pune, Maharashtra that checks RERA compliance, queries building regulations via RAG, and produces structured permit feasibility reports.

> Think "Claude Code for land" — but for Indian municipal permitting.

## What it does

Given a plot query (address, survey number, or coordinates), rerAI:

1. **Plans** the assessment via an internal task list
2. **Delegates** to specialized subagents for parallel data gathering
3. **Synthesizes** findings into a structured permit feasibility report

### Current data pillars

| Pillar | Status | Subagent | Data Source |
|---|---|---|---|
| RERA Compliance | Phase 1 | `rera-analyst` | MahaRERA portal scraping |
| Building Regulations | Phase 1 | `regulatory-checker` | UDCPR 2025 PDF (576 pages, ChromaDB RAG) |
| GIS Spatial | Phase 2 | `gis-analyst` | Bhuvan WMS, PMC Open Data, OpenStreetMap |
| Land Records | Phase 2 | `title-verifier` | Mahabhulekh 7/12 extracts via Playwright |
| Environmental | Phase 3 | `environmental-checker` | PARIVESH, eco-sensitive zone boundaries |

## Architecture

```
User Query
    │
    ▼
┌─────────────────────────────────┐
│   Orchestrator (deepagents)     │
│   qwen/qwen3.6-plus:free        │
│   via OpenRouter                 │
├─────────────────────────────────┤
│  ┌──────────┐  ┌──────────────┐ │
│  │ rera-    │  │ regulatory-  │ │
│  │ analyst  │  │ checker      │ │
│  │ (nemotron│  │ (nemotron)   │ │
│  └──────────┘  └──────────────┘ │
└─────────────────────────────────┘
    │
    ▼
Permit Feasibility Report
```

Built on [deepagents](https://github.com/langchain-ai/deepagents) — LangChain's agent orchestration framework over LangGraph. Each subagent runs with context isolation: heavy scraping/vector search stays in the subagent, only synthesized results return to the orchestrator.

## Setup

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- [Ollama](https://ollama.ai) running locally with `embeddinggemma:latest` pulled
- OpenRouter API key

### Install

```bash
git clone https://github.com/parthashirolkar/rerAI.git
cd rerAI
uv sync
```

### Configure

Create a `.env` file (already gitignored):

```
OPENROUTER_API_KEY=sk-or-v1-...
OLLAMA_BASE_URL=http://localhost:11434/v1
```

### Pull embedding model

```bash
ollama pull embeddinggemma:latest
```

## Usage

```bash
uv run python main.py
```

This will:
1. Ingest the UDCPR PDF into ChromaDB (first run only, ~1625 chunks)
2. Start an interactive REPL

Example queries:
- "What are the FSI limits for a residential plot in Pune?"
- "Search for RERA projects in Pune district"
- "Check permit feasibility for survey number 123 in Haveli taluka"

## Project Structure

```
rerAI/
├── main.py                    # Orchestrator REPL
├── tools/
│   ├── config.py              # LLM + embedding config
│   ├── rera_tools.py          # MahaRERA search/lookup tools
│   └── regulatory_tools.py    # UDCPR RAG query tool
├── subagents/
│   └── definitions.py         # Subagent configurations
├── memory/
│   └── AGENT_KNOWLEDGE.md     # Pune context (loaded at runtime)
├── skills/
│   └── permit-feasibility/    # Permit assessment skill
├── data/
│   ├── pdfs/                  # UDCPR PDFs (gitignored)
│   └── chroma_db/             # Vector store (gitignored)
├── ROADMAP.md                 # Phase 2-3 implementation spec
└── pyproject.toml
```

## Roadmap

See [ROADMAP.md](./ROADMAP.md) for detailed Phase 2 (GIS + Land Records) and Phase 3 (Environmental + Synthesis) specifications.

## License

MIT
