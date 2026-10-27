# AI 运营 SaaS 平台 — System Architecture

## 1. System Overview

The platform is a multi-tenant SaaS service that provides AI-powered operations tooling for hotel and hospitality businesses. Tenants ("organizations") onboard human staff as digital employees backed by LangGraph agent workflows, automate routine operations tasks, and produce marketing video content through an AI pipeline.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Client Layer                                     │
│                                                                             │
│   ┌──────────────────────┐          ┌───────────────────────────────────┐  │
│   │  Vue 3 Web Dashboard  │          │  WeChat Mini Program (uni-app)    │  │
│   │  (Naive UI, Pinia)    │          │  Staff mobile interface           │  │
│   └──────────┬───────────┘          └────────────────┬──────────────────┘  │
└──────────────┼──────────────────────────────────────-┼─────────────────────┘
               │  HTTPS / REST + WebSocket             │  HTTPS
               ▼                                       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                             API Gateway / Nginx                              │
│              /api/* → backend:8000    /* → frontend static                  │
└──────────────────────────────┬───────────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         FastAPI Application                                  │
│                                                                              │
│  ┌─────────────┐  ┌────────────────┐  ┌─────────────────┐  ┌─────────────┐ │
│  │  Auth/Tenants│  │  Agent Runtime │  │  Video Pipeline │  │  Hotel API  │ │
│  │  (JWT+RBAC)  │  │  (LangGraph)   │  │  (FFmpeg+AI)    │  │  Connector  │ │
│  └─────────────┘  └───────┬────────┘  └────────┬────────┘  └─────────────┘ │
└──────────────────────────-┼──────────────────-─┼──────────────────────────-─┘
                            │                    │
               ┌────────────┘                    └──────────────┐
               ▼                                                ▼
┌──────────────────────────┐                     ┌─────────────────────────────┐
│     Celery Workers        │                     │      External AI APIs       │
│  (Redis broker + backend) │                     │  OpenAI / Seedance / etc.   │
│                           │                     └─────────────────────────────┘
│  ┌────────────────────┐   │
│  │  LangGraph tasks   │   │
│  │  Video render tasks│   │
│  │  Scheduled jobs    │   │
│  └────────────────────┘   │
└──────────────────────────-┘
               │
               ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                           Persistence Layer                                  │
│                                                                              │
│   ┌────────────────┐   ┌──────────────────┐   ┌──────────────────────────┐  │
│   │  PostgreSQL 16  │   │    Redis 7        │   │   MinIO / S3             │  │
│   │  Primary store  │   │  Cache + broker   │   │  Files, videos, assets   │  │
│   └────────────────┘   └──────────────────┘   └──────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Technology Stack Decisions

| Layer | Choice | Rationale |
|---|---|---|
| API framework | FastAPI | Async-capable, automatic OpenAPI docs, Pydantic validation, Python 3.11 |
| Agent orchestration | LangGraph | Stateful graph workflows, built-in checkpointing, native LangChain ecosystem |
| Frontend | Vue 3 + Vite | Composition API, strong TypeScript story, smaller bundle than React for dashboard use |
| Component library | Naive UI | Tree-shakable, TypeScript-first, consistent dark/light theming via design tokens |
| State management | Pinia | Simpler than Vuex, composition-API-style stores, first-party Vue 3 support |
| Task queue | Celery + Redis | Mature Python ecosystem, Redis doubles as cache and broker, Flower monitoring |
| ORM | SQLAlchemy 2.0 (sync) | Widely understood, robust migration tooling via Alembic, sync chosen for initial simplicity |
| Database | PostgreSQL 16 | Row-level security available for tenant isolation, JSONB for flexible agent state |
| Object storage | MinIO (dev) / S3 (prod) | S3-compatible API means zero code changes between environments |
| Video processing | FFmpeg | LGPL, universal codec support, runs headless in containers |
| Mini program | uni-app + Vue 3 | Single codebase targets WeChat, Alipay, H5; reuses Vue skills from web frontend |

---

## 3. Multi-Tenant Data Isolation Strategy

Every resource-bearing table carries an `organization_id` foreign key. Isolation is enforced at three layers:

**Application layer (primary):** All repository/service functions accept an `organization_id` parameter derived from the authenticated JWT claim. No query is issued without filtering by this value. SQLAlchemy session factories are wrapped in a `TenantSession` context that automatically appends `WHERE organization_id = :oid` to every query through a custom `QueryFilter` event listener.

**Database layer (secondary):** PostgreSQL row-level security (RLS) policies are defined on sensitive tables as a defense-in-depth measure. RLS is disabled by default in development to ease migrations and local testing; it is enabled in production via an environment flag applied during migration.

**Validation layer:** Pydantic schemas on every inbound request include a `organization_id` field that is compared against the token claim. A mismatch raises HTTP 403 before any database access occurs.

Cross-tenant access is only possible for superadmin roles, which require a separate `is_superadmin` claim that is never issued to regular tenants.

---

## 4. Agent Runtime Design (LangGraph)

Digital employees are modelled as LangGraph state machines. Each agent type (receptionist, marketing assistant, operations planner, etc.) is a directed graph where nodes are callable functions and edges encode conditional logic.

```
┌──────────────────────────────────────────────────────────────────────────┐
│                     Agent Execution Graph (example)                      │
│                                                                          │
│  START → [receive_task] → [classify_intent] ──► [tool_call_node]        │
│                                  │                      │               │
│                                  ▼                      ▼               │
│                          [direct_response]      [await_tool_result]     │
│                                  │                      │               │
│                                  └──────────┬───────────┘               │
│                                             ▼                           │
│                                    [compose_response]                   │
│                                             │                           │
│                                             ▼                           │
│                                  [human_review_gate?] ──► [escalate]   │
│                                             │                           │
│                                             ▼                           │
│                                           END                           │
└──────────────────────────────────────────────────────────────────────────┘
```

**State schema:** Each graph holds a typed `TypedDict` state including `messages`, `task_id`, `organization_id`, `tool_outputs`, and `requires_human_review`. State is persisted to PostgreSQL via LangGraph's checkpoint interface after each node execution, enabling pause/resume and audit replay.

**Tool registry:** Each agent type declares a list of allowed tools (e.g. `search_orders`, `send_notification`, `create_video_project`). Tools are Python callables registered with LangChain's `@tool` decorator. Tenant-scoped tools receive the organization ID from the graph state automatically.

**Celery integration:** Long-running agent executions are dispatched as Celery tasks. The API returns a `task_id` immediately; the frontend polls `/api/v1/tasks/{task_id}/status` or subscribes via WebSocket for real-time updates.

**Human-in-the-loop:** The `human_review_gate` node checks a configurable threshold (confidence score, task type, dollar value). Below the threshold, execution pauses and a review request is created in the database. A human approves or rejects via the dashboard, which resumes the graph from its persisted checkpoint.

---

## 5. Video Creation Pipeline

Two modes share the same underlying pipeline but diverge at the script/shot-planning stage.

**Mode A — AI Creative:**
1. User provides a topic, tone, target audience, and optional brand assets.
2. An LLM call generates a full script with shot descriptions.
3. The shot plan is decomposed into individual `Shot` records in the database.
4. Each shot is dispatched as a Celery task to the AI video provider (Seedance or mock).
5. Generated clips are downloaded to S3.
6. The synthesis worker runs FFmpeg to concatenate clips, overlay captions, apply brand watermark, and normalize audio.
7. The final video is uploaded to S3 and the `VideoProject` state transitions to `COMPLETE`.

**Mode B — Reference-Inspired:**
1. User uploads a reference video.
2. A vision model analyzes the reference and extracts style, pacing, and shot structure.
3. Steps 2–7 from Mode A proceed, with extracted style tokens injected into the LLM prompt.

Both modes emit webhook events at state transitions so the frontend can update in real time without polling.

---

## 6. Storage Strategy

| Environment | Backend | Notes |
|---|---|---|
| Development | MinIO (Docker service) | S3-compatible; no AWS account needed; data persists in Docker volume |
| Staging | AWS S3 or MinIO on VM | Real S3 recommended to catch IAM issues before production |
| Production | AWS S3 | Bucket-per-tenant recommended for IAM isolation; CloudFront for CDN delivery |

The application references storage through a `StorageClient` abstraction (`app/storage/client.py`). Switching backends is a single environment variable change (`STORAGE_BACKEND`, `S3_ENDPOINT_URL`). The client exposes `upload`, `download`, `get_presigned_url`, and `delete` operations; the rest of the codebase never imports boto3 directly.

---

## 7. Authentication and Authorization Flow

```
Client                          API                        Database
  │                              │                              │
  │── POST /auth/login ─────────►│                              │
  │   {username, password}       │── SELECT user WHERE email ──►│
  │                              │◄── user record ──────────────│
  │                              │── bcrypt.verify() ───────────│
  │◄── {access_token,            │                              │
  │     refresh_token} ──────────│                              │
  │                              │                              │
  │── GET /api/v1/resource ─────►│                              │
  │   Authorization: Bearer JWT  │── decode JWT ────────────────│
  │                              │── verify exp, iss, org_id ───│
  │                              │── attach user to request ────│
  │                              │── check RBAC permission ─────│
  │◄── 200 response ─────────────│                              │
```

**Token structure:** JWTs carry `sub` (user UUID), `org` (organization UUID), `roles` (list), `exp`, and `iss`. Access tokens expire in 15 minutes; refresh tokens in 7 days, stored server-side in Redis for revocation support.

**RBAC:** Roles are `owner`, `admin`, `manager`, `staff`. Permissions are checked via a decorator `@require_permission("resource:action")` applied to route handlers. The permission matrix is defined in `app/auth/permissions.py`.

**WeChat login:** The mini program calls WeChat's `wx.login()` to obtain a `code`, sends it to `POST /auth/wechat/login`, which exchanges it for an `openid` via the WeChat server-side API, then either retrieves an existing user or creates one, and returns standard JWT tokens.

---

## 8. Async Task Processing Design

```
FastAPI Route Handler
       │
       │ .delay() or .apply_async()
       ▼
   Redis (broker)
       │
       │ task dequeued
       ▼
Celery Worker Process
       │
       ├── app.tasks.agent_tasks    (LangGraph executions)
       ├── app.tasks.video_tasks    (video generation + FFmpeg)
       └── app.tasks.notification_tasks (WeChat, email)
       │
       │ result / status update
       ▼
   Redis (result backend)
       │
       ▼
FastAPI /tasks/{id}/status endpoint
```

**Beat schedule:** Celery Beat runs periodic tasks — nightly data sync with hotel connector, daily report generation, token cleanup. The schedule is defined in `app/worker/schedule.py` and loaded by the beat process.

**Task retry policy:** All tasks define `max_retries=3` with exponential backoff (`countdown=2 ** retry_count * 60`). Failed tasks after all retries are written to a `FailedTask` table for manual review.

**Concurrency:** Workers run with `--concurrency=4` in production. Video tasks are routed to a dedicated `video` queue with a separate worker pool to prevent heavy rendering work from starving lightweight API tasks.

---

## 9. API Design Principles

- All routes are versioned under `/api/v1/`.
- Resources use plural nouns: `/organizations`, `/agents`, `/video-projects`.
- Actions that don't map to CRUD use verb sub-resources: `/video-projects/{id}/publish`, `/agents/{id}/pause`.
- Pagination uses cursor-based pagination (not offset) for large collections: `?cursor=<opaque_token>&limit=50`.
- All timestamps are ISO 8601 UTC.
- Error responses follow RFC 9457 Problem Details: `{"type": "...", "title": "...", "detail": "...", "status": 422}`.
- File uploads use multipart form data to `/api/v1/uploads`; the endpoint returns a storage key used in subsequent resource creation calls.

---

## 10. Security Considerations

**API keys:** Never stored in the database. All third-party API keys live in environment variables, loaded at startup. The application logs a warning on startup if a key is empty and marks the relevant feature as unavailable.

**File upload validation:** Uploaded files are validated for MIME type (using `python-magic`, not the `Content-Type` header), size limits, and virus-scanned if a ClamAV sidecar is configured. Files are stored with random UUIDs as keys, never with user-supplied filenames.

**SQL injection:** SQLAlchemy parameterized queries throughout; no raw SQL strings constructed with user input. The rare cases of dynamic ORDER BY columns use an allowlist.

**Rate limiting:** FastAPI middleware applies per-IP and per-user rate limits using a Redis sliding window. Limits are tighter on authentication endpoints.

**Secrets rotation:** The `SECRET_KEY` (JWT signing) can be rotated by adding a `SECRET_KEY_PREVIOUS` environment variable during a rolling deployment. The auth middleware accepts tokens signed by either key for one rotation window.

**Audit log:** Every mutating API call writes a record to `audit_log` with `user_id`, `organization_id`, `action`, `resource_type`, `resource_id`, `ip_address`, and `timestamp`. Audit records are append-only (no UPDATE or DELETE exposed).

**Known limitations (Phase 1):** RLS is defined but not enforced in development; must be verified in staging before production launch. WeChat login requires real credentials and HTTPS; mock mode is available for local development. File virus scanning is optional and disabled by default.
