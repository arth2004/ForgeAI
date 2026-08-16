# Forge AI

**Forge AI** is an enterprise-grade AI software engineering platform. Rather than acting as a superficial wrapper around an LLM chat endpoint, Forge AI connects directly to GitHub repositories, continuously indexes codebase structure, commits, symbols, and documentation, and executes multi-step autonomous engineering workflows via **LangGraph**, **pgvector**, and the **Model Context Protocol (MCP)**.

---

## Current Phase

**Phase 1 — Foundational Platform**

> [!NOTE]
> Phase 1 establishes the production-oriented monorepo foundation, Next.js application shell, FastAPI backend, PostgreSQL 16 + pgvector migrations, Redis cache/broker, ARQ background worker, authentication foundation, and Docker Compose orchestration.
>
> Ingestion, Tree-sitter parsing, embedding generation, pgvector retrieval, and LangGraph agents belong to subsequent phases.

---

## Tech Stack (Phase 1 Implemented)

- **Frontend**: Next.js 15 (App Router), React 19, TypeScript, Tailwind CSS, TanStack Query, Lucide Icons
- **Backend API**: Python 3.12+, FastAPI, SQLAlchemy 2.0 (Async), Pydantic v2, Pydantic-Settings
- **Database & Storage**: PostgreSQL 16 with `pgvector` extension, Alembic migrations
- **Cache & Async Queue**: Redis 7, ARQ (Async Redis Queue)
- **Security**: AES-256-GCM authenticated credential encryption, HMAC-SHA256 JWT, Bcrypt password hashing
- **Testing & Quality**: Pytest, Pytest-Asyncio, Vitest, React Testing Library, Ruff, Mypy
- **Orchestration**: Docker Compose

---

## Monorepo Structure

```text
ForgeAi/
├── .github/
│   └── workflows/              # GitHub Actions CI workflows
│       ├── ci-backend.yml
│       ├── ci-frontend.yml
│       └── lint-and-typecheck.yml
├── docs/                       # Architecture, Decision Records, and Roadmap
│   ├── architecture.md
│   ├── decisions.md
│   └── roadmap.md
├── frontend/                   # Next.js 15 App Router Frontend
│   ├── src/
│   │   ├── app/                # Pages and layouts
│   │   ├── components/         # Layout & UI components
│   │   ├── lib/                # API client & Query client
│   │   └── types/              # TypeScript definitions
│   └── tests/                  # Vitest suite
├── backend/                    # FastAPI Backend Application
│   ├── app/
│   │   ├── api/v1/             # REST endpoints (health, auth, orgs, projects, worker)
│   │   ├── core/               # Config, database, security, redis, telemetry
│   │   ├── models/             # SQLAlchemy 2.0 ORM models
│   │   ├── schemas/            # Pydantic schemas
│   │   ├── services/           # Domain business logic
│   │   └── workers/            # ARQ background worker & tasks
│   ├── alembic/                # PostgreSQL & pgvector migrations
│   └── tests/                  # Pytest unit and integration test suite
├── docker-compose.yml          # Multi-container local orchestration
├── .env.example                # Configuration template
└── README.md
```

---

## Running Locally with Docker Compose

### 1. Configure Environment

Copy the example environment file:

```bash
cp .env.example .env
```

### 2. Start All Services

```bash
docker compose up --build
```

This starts 5 coordinated services:
- **PostgreSQL 16 + pgvector**: `localhost:5432`
- **Redis 7**: `localhost:6379`
- **FastAPI Backend**: `http://localhost:8000` (Docs: `http://localhost:8000/api/v1/docs`)
- **ARQ Worker**: Async background job consumer
- **Next.js Frontend**: `http://localhost:3000`

---

## Services & Ports

| Service | Technology | Port | Description |
| :--- | :--- | :--- | :--- |
| **Frontend** | Next.js 15 / React 19 | `3000` | Developer Workspace UI & Dashboards |
| **API Gateway** | FastAPI / Uvicorn | `8000` | Async REST API & SSE Streaming |
| **PostgreSQL** | Postgres 16 + pgvector | `5432` | Relational metadata & Vector persistence |
| **Redis** | Redis 7 Alpine | `6379` | Cache, Broker & ARQ Queue backend |
| **ARQ Worker** | Python Asyncio | N/A | Background task processing engine |

---

## Database & Migrations

Database schema migrations are managed via **Alembic** with automated `pgvector` extension provisioning.

To apply migrations manually:

```bash
cd backend
alembic upgrade head
```

To create a new migration:

```bash
cd backend
alembic revision --autogenerate -m "describe_migration"
```

---

## Testing & Quality

### Backend Tests

Run unit and integration tests with pytest:

```bash
cd backend
pytest -v
```

Run linting:

```bash
cd backend
ruff check .
```

### Frontend Tests

Run Vitest unit tests:

```bash
cd frontend
npm test
```

Run TypeScript typecheck:

```bash
cd frontend
npm run typecheck
```

---

## Health Check & Verification

Verify the system health endpoint:

```bash
curl http://localhost:8000/api/v1/health
```

Expected JSON response:

```json
{
  "status": "ok",
  "version": "0.1.0",
  "services": {
    "database": "ok",
    "redis": "ok",
    "worker_queue": "ok"
  }
}
```

---

## Roadmap

Refer to [docs/roadmap.md](docs/roadmap.md) for the complete phase breakdown:

- **Phase 1 (Current)**: Foundational Platform
- **Phase 2**: GitHub Integration & Repository Linking
- **Phase 3**: Repository Ingestion & Tree-Sitter Hybrid Retrieval
- **Phase 4**: Project-Aware AI Assistant (LangGraph + SSE Stream)
- **Phase 5**: Agent Platform (Multi-Hop Dependency Traversal)
- **Phase 6**: Developer Workflows (PR Reviewer, Architecture Map)
- **Phase 7**: Model Context Protocol (MCP)
- **Phase 8**: AI Evaluation & Observability
- **Phase 9**: Production Hardening
