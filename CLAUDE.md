# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Korean legal document review multi-agent system. Three modes: **Review** (contract risk analysis), **Draft** (contract generation via interview), **Advise** (legal Q&A chat). Built with LangGraph orchestrator pattern, FastAPI backend, Next.js frontend.

## Commands

### Backend (Python)
```bash
# Install dependencies
pip install -e ".[dev]"

# Run API server
uvicorn app.main:app --reload --port 8000

# Run all tests
pytest

# Run single test file
pytest tests/test_parsers/test_clause_splitter.py

# Run single test class/method
pytest tests/test_parsers/test_clause_splitter.py::TestKoreanClauseSplitter::test_standard_format

# Lint
ruff check app/ tests/
ruff format app/ tests/
```

### Frontend (Next.js, in `web/` directory)
```bash
cd web
npm install
npm run dev      # dev server
npm run build    # production build
npm run lint     # ESLint
```

### Infrastructure (Docker)
```bash
docker-compose up -d db redis   # DB + Redis only (local dev)
docker-compose up               # full stack including API + Celery worker
```

## Architecture

### Agent Orchestration (LangGraph)

The system uses a **top-level orchestrator** (`app/graphs/orchestrator.py`) that classifies user intent and routes to one of three sub-graphs:

1. **Review Graph** (`app/graphs/review_graph.py`): SecurityScan → Parse → [Analyzer + RAG parallel] → Merge → Validate → retry loop (max 2)
2. **Draft Graph** (`app/graphs/draft_graph.py`): Interview (multi-turn) → SearchTemplate → Generate → SelfReview → revise loop → Export DOCX
3. **Advise Graph** (`app/graphs/advise_graph.py`): LoadSession → ExtractClause → RAGSearch → GenerateAdvice → UpdateSession

Each graph's state is defined in `app/state/` (e.g., `ReviewState`, `DraftState`, `AdviseState`). Graph nodes live in `app/nodes/`.

### LLM Integration

- **LiteLLM** (`app/llm/client.py`) abstracts all LLM calls — supports both Anthropic and OpenAI models via `call_llm()` / `call_llm_json()`
- Model assignments are configurable via env vars: `ANALYZER_MODEL`, `VALIDATOR_MODEL`, `CLASSIFIER_MODEL`, `DRAFTER_MODEL`, `ADVISOR_MODEL`
- System prompts for each agent role live in `app/llm/prompts/`

### RAG & Database

- PostgreSQL with **pgvector** for vector similarity search
- Hybrid search (vector + keyword with RRF fusion) via SQL functions `hybrid_search_laws()` and `hybrid_search_precedents()` defined in `migrations/001_initial_schema.sql`
- Embedding model: `text-embedding-3-small` (1536 dimensions)
- RAG knowledge base tables: `laws`, `precedents`, `standard_clauses`
- Ingestion scripts in `scripts/` (ingest_laws, ingest_precedents, ingest_standard_clauses)

### API Structure

All routes under `/api/v1/` — modules in `app/api/v1/`: documents, analysis, draft, advise, precedents, reports.

### Frontend

Next.js 15 + React 19 app in `web/`. Custom hooks (`web/src/hooks/`) manage API calls for each mode. Uses Tailwind CSS + Radix UI primitives.

## Key Conventions

- Code comments and UI strings are in **Korean** (한국어)
- Python 3.11+, Ruff for linting (line-length 100, rules: E/F/I/W)
- Tests use **pytest-asyncio** with `asyncio_mode = "auto"`
- Pydantic v2 models in `app/models/`, settings via `pydantic-settings` in `app/config.py`
- Config loads from `.env` file — see `.env.example` for required variables
