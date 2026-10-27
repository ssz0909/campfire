# 营火AI · AI运营平台

Always on, Always Growing.

Multi-tenant SaaS platform for AI-powered hospitality operations. Provides digital employees backed by LangGraph agent workflows, a two-mode AI video creation pipeline, and a hotel order management connector.

---

## Architecture Overview

```
Vue 3 Dashboard + WeChat Mini Program
           │
    nginx (TLS termination, reverse proxy)
           │
    FastAPI (REST API, WebSocket)
           │
    Celery Workers  ←→  Redis (broker + cache)
           │
    PostgreSQL 16   MinIO / S3
```

Primary stack: Python 3.11 / FastAPI / SQLAlchemy 2.0 / LangGraph on the backend; Vue 3 / Naive UI / Pinia on the frontend; uni-app for the WeChat mini program.

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Mac/Windows) or Docker Engine + Compose v2 (Linux)
- Git

No local Python or Node installation is required — all tooling runs inside Docker.

---

## Quick Start

```bash
git clone https://github.com/ssz0909/campfire.git
cd campfire

# Create your local environment file — defaults work out of the box
cp .env.example .env

# Start all services
docker-compose up -d

# Apply database migrations
docker-compose exec backend alembic upgrade head

# Create the first organization and admin user
docker-compose exec backend python -m app.cli create-superadmin \
  --email admin@example.com \
  --password your-password \
  --org-name "My Organization"
```

Open http://localhost:5173 to access the dashboard.

Other endpoints:
- API documentation: http://localhost:8000/docs
- Task monitor (Flower): http://localhost:5555
- MinIO console: http://localhost:9001

---

## Development Setup

All services run in Docker. Source files are mounted as volumes, so changes to `backend/` and `frontend/` reload automatically without rebuilding images.

**Backend hot reload:** The backend uses `uvicorn --reload`. Edit any Python file and the server restarts within a second.

**Frontend hot reload:** Vite's HMR is active. Edit any `.vue` or `.ts` file and the browser updates without a full page reload.

**Installing new backend dependencies:**
```bash
# Add to backend/requirements.txt, then:
docker-compose build --no-cache backend
docker-compose up -d backend celery_worker celery_beat
```

**Installing new frontend dependencies:**
```bash
docker-compose exec frontend npm install <package>
# package.json and package-lock.json are in the volume, so changes persist
```

**Creating a new database migration:**
```bash
# After changing a SQLAlchemy model:
docker-compose exec backend alembic revision --autogenerate -m "add video project model"
# Review the generated file in backend/alembic/versions/ before committing
docker-compose exec backend alembic upgrade head
```

---

## Running Tests

**Backend:**
```bash
docker-compose exec backend pytest
docker-compose exec backend pytest --cov=app --cov-report=term-missing
```

**Frontend:**
```bash
docker-compose exec frontend npm run test
docker-compose exec frontend npm run typecheck
```

---

## Project Structure

```
AIwork/
├── backend/
│   ├── app/
│   │   ├── api/          FastAPI routers
│   │   ├── auth/         JWT, RBAC, WeChat login
│   │   ├── connectors/   Hotel API connector (Dingdanlaile)
│   │   ├── core/         Settings, database session, dependencies
│   │   ├── models/       SQLAlchemy models
│   │   ├── schemas/      Pydantic request/response schemas
│   │   ├── services/     Business logic
│   │   ├── storage/      S3/MinIO abstraction
│   │   ├── video/        Video creation pipeline
│   │   └── worker/       Celery tasks and beat schedule
│   ├── alembic/          Database migrations
│   ├── tests/
│   ├── Dockerfile
│   ├── Dockerfile.dev
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/   Shared UI components
│   │   ├── pages/        Route-level views
│   │   ├── stores/       Pinia stores
│   │   ├── composables/  Vue composition utilities
│   │   └── api/          Generated API client
│   ├── Dockerfile
│   └── Dockerfile.dev
├── miniprogram/          WeChat mini program (uni-app, Phase 5)
├── docs/                 Architecture and planning documents
├── shared/               Types shared between backend and frontend
├── docker-compose.yml    Development environment
├── docker-compose.prod.yml  Production environment
└── .env.example          Environment variable template
```

---

## Phase 1 Status

### What works (no external credentials needed)

- Docker Compose development environment — all services start healthy
- Multi-tenant data model with organization and user management
- JWT authentication (register, login, refresh, logout)
- RBAC with four roles: owner, admin, manager, staff
- Database migrations via Alembic
- Vue 3 dashboard shell with login, organization switcher, sidebar
- Mock LLM responses for agent workflows (set `USE_MOCK_DATA=true`)
- Mock video generation pipeline (set `VIDEO_PROVIDER=mock`)
- MinIO object storage for local file handling
- Celery + Flower task monitoring

### What requires real credentials to activate

| Feature | Credential needed | Status |
|---|---|---|
| LLM-powered agents | `OPENAI_API_KEY` | Pending — mock available |
| AI video generation | `SEEDANCE_API_KEY` | Pending — mock available |
| Hotel order connector | Dingdanlaile API key + sandbox | Pending — see `docs/api_integration.md` |
| WeChat mini program login | `WECHAT_APP_ID` + `WECHAT_APP_SECRET` | Pending — see `docs/wechat_miniapp_spec.md` |

---

## Documentation

| Document | Contents |
|---|---|
| `docs/architecture.md` | System overview, technology decisions, data flow |
| `docs/development_plan.md` | Six-phase development plan with acceptance criteria |
| `docs/tech_decisions.md` | ADR-style records for all major technical choices |
| `docs/deployment.md` | Local setup, migration commands, production checklist |
| `docs/security.md` | Tenant isolation, authentication, audit log |
| `docs/api_integration.md` | Third-party integration configuration |
| `docs/video_creation_product_spec.md` | Video pipeline design and state machines |
| `docs/wechat_miniapp_spec.md` | Mini program scope and configuration checklist |
| `docs/ui_design_system.md` | Color tokens, typography, component conventions |
| `docs/oss_compliance.md` | Open source license review and action items |

---

## Contributing

1. Work in a feature branch: `git checkout -b feature/your-feature`
2. Write tests for new behavior; run `pytest` before opening a PR
3. Keep migrations focused — one logical change per migration file
4. Do not commit `.env` or any file containing real credentials
5. Run `docker-compose exec frontend npm run typecheck` before frontend PRs
6. Open a PR against `main`; describe what changed and how to test it
