# Technology Decisions

Architecture Decision Records for the AI 运营 SaaS platform.

---

## ADR-001: FastAPI over Django or Flask

**Status:** Accepted

**Context:** The backend serves a REST API consumed by a Vue SPA and a WeChat mini program. It also runs background agent workflows. We considered Django REST Framework, Flask + extensions, and FastAPI.

**Decision:** FastAPI.

**Rationale:**
- Automatic OpenAPI schema generation from type hints eliminates a maintenance burden. The schema drives frontend client generation and is the primary API contract document.
- Pydantic v2 validation is fast, composable, and catches data shape errors at the boundary before they propagate.
- Async support is built-in; we can incrementally adopt async I/O where it matters (HTTP calls to external AI APIs) without rewriting the app.
- Django's ORM and admin are attractive but we are not building a content-management system. The Django ecosystem's conventions solve problems we don't have and impose structure around the ones we do.
- Flask gives us fewer constraints but also fewer built-in solutions; we'd end up assembling Flask + Marshmallow + apispec + extensions — that's DX overhead with no gain over FastAPI.

**Trade-offs:** FastAPI's ecosystem is younger than Django's. Some Django packages (django-guardian, django-auditlog) have no direct FastAPI equivalent and must be built. We accept this cost given the API-first architecture.

---

## ADR-002: LangGraph for Agent Orchestration

**Status:** Accepted

**Context:** Digital employees need to execute multi-step workflows with branching logic, tool calls, human-in-the-loop pauses, and resumable state. Alternatives considered: plain Python state machines (transitions library), LangChain's legacy AgentExecutor, custom Celery chains.

**Decision:** LangGraph.

**Rationale:**
- LangGraph represents workflow state as a typed graph with explicit edges and a persistent checkpoint. This is exactly the model we need for pause/resume and audit replay.
- The checkpoint interface integrates with PostgreSQL via a SQLAlchemy checkpoint adapter, so agent state lives next to business data rather than in a separate store.
- The graph structure makes human-review gates a first-class concept: the graph pauses at a conditional edge and waits for an external signal to resume.
- Compared to AgentExecutor, LangGraph gives us full visibility into execution steps and explicit control over state mutations.
- Custom Celery chains could represent a workflow but they cannot resume from an arbitrary mid-point; each retry restarts the entire chain.

**Trade-offs:** LangGraph is relatively new (2024). Breaking changes are possible. We pin the version tightly and abstract the checkpoint layer so a migration is localized if needed.

---

## ADR-003: Naive UI for Frontend Component Library

**Status:** Accepted

**Context:** The Vue 3 dashboard needs a component library. Options considered: Element Plus, Ant Design Vue, Vuetify 3, Naive UI, PrimeVue.

**Decision:** Naive UI.

**Rationale:**
- Naive UI is TypeScript-first and built for Vue 3 from the ground up — not ported from a Vue 2 library.
- The theming system is token-based (CSS variables generated from a design token object). This makes implementing the OKLCH color system straightforward: override the token object, the rest propagates.
- Tree-shaking is effective; unused components add no bundle weight.
- Element Plus and Ant Design Vue both carry larger bundles and their theming requires CSS variable hacks. Vuetify 3 is strong but Material Design opinionated. PrimeVue's theming in v3 is strong but the component API is inconsistent.
- Naive UI's data table component handles the sticky headers, sortable columns, and pagination the operations dashboard needs without customization.

**Trade-offs:** Naive UI has a smaller community than Element Plus. Some specialized components (rich text editor, Gantt chart) are not in the library and need third-party additions.

---

## ADR-004: Celery + Redis for Async Task Processing

**Status:** Accepted

**Context:** Agent executions, video generation, and periodic syncs are long-running or compute-heavy operations that cannot block the HTTP request cycle. Options: FastAPI BackgroundTasks, Celery, ARQ (async-native), Dramatiq.

**Decision:** Celery with Redis as broker and result backend.

**Rationale:**
- Celery is the most mature Python task queue with the widest ecosystem. The retry policies, routing, and priority queues we need are built-in.
- Redis already exists in the stack as a cache; using it as the Celery broker avoids adding RabbitMQ.
- Flower provides an out-of-the-box monitoring UI for task state, worker status, and queue depth. This is operationally valuable from day one.
- FastAPI BackgroundTasks run in-process; a worker crash loses all enqueued work. Celery tasks survive process restarts.
- ARQ is simpler and async-native but lacks Celery's retry strategies and has minimal monitoring tooling.

**Trade-offs:** Celery adds operational complexity (worker processes, beat process, broker). The learning curve is manageable and the operational cost is justified by the reliability and observability gains.

---

## ADR-005: SQLAlchemy 2.0 with Synchronous Sessions

**Status:** Accepted

**Context:** SQLAlchemy 2.0 supports both sync and async session styles. Async SQLAlchemy + asyncpg offers lower latency under I/O-heavy workloads. We considered starting with async.

**Decision:** Synchronous sessions with `psycopg2`.

**Rationale:**
- Async SQLAlchemy introduces significant complexity: session lifecycle in async context managers, lazy-loading restrictions, and testing difficulties (asyncpg test fixtures are non-trivial).
- Most of the application's database interactions happen inside Celery workers, which are synchronous by nature. Mixing async and sync SQLAlchemy in the same codebase creates two session patterns to maintain.
- FastAPI's `Depends()` works cleanly with synchronous generators. The performance difference is not measurable at the scale of Phase 1.
- This is explicitly a "start simple, migrate if needed" decision. SQLAlchemy 2.0's `async_sessionmaker` is available when we need it; the migration is confined to the session factory and repository layer.

**Trade-offs:** Under high concurrency, sync sessions block threads. Uvicorn workers handle this via thread pool for sync routes (`run_in_threadpool`). We will revisit if profiling shows thread exhaustion.

---

## ADR-006: PostgreSQL over MySQL, MongoDB, or SQLite

**Status:** Accepted

**Context:** Primary relational store for all business data. Alternatives considered.

**Decision:** PostgreSQL 16.

**Rationale:**
- Row-level security (RLS) provides a database-enforced second layer of tenant isolation. No other common RDBMS provides comparable RLS ergonomics.
- JSONB columns store flexible agent state and configuration without requiring schema changes for each new agent type.
- Full-text search (`tsvector`) is available without a separate search service for the initial implementation.
- `pg_vector` extension is available for semantic similarity search on agent knowledge bases — a planned future feature.
- MySQL lacks RLS. MongoDB's flexible schema is not needed; our data is relational. SQLite is unsuitable for multi-process concurrent writes.

**Trade-offs:** PostgreSQL requires more configuration than SQLite or MySQL for replication and backup. Cloud-managed PostgreSQL (RDS, Cloud SQL, Supabase) eliminates most of this burden in production.

---

## ADR-007: UUID Primary Keys

**Status:** Accepted

**Context:** Primary key strategy for all models.

**Decision:** UUID v4 as primary keys (stored as `UUID` type in PostgreSQL).

**Rationale:**
- UUIDs do not leak sequential record counts to API consumers.
- IDs can be generated client-side or in application code before the database write, enabling optimistic creation patterns.
- No cross-tenant ID collision is possible, which matters when joining across tables in superadmin contexts.
- Avoids the "expose integer ID in URL" anti-pattern that lets users enumerate resources.

**Trade-offs:** UUIDs are larger than integers (16 bytes vs 4 or 8) and random UUIDs fragment B-tree indexes. We use `gen_random_uuid()` which is sufficient at our scale. UUIDv7 (time-ordered) is available as a future optimization if index fragmentation becomes measurable.

---

## ADR-008: Soft Deletes Strategy

**Status:** Accepted

**Context:** When a user deletes a digital employee, video project, or organization resource, we need to decide whether to hard-delete or soft-delete.

**Decision:** Soft deletes via `deleted_at` timestamp column on deletable models.

**Rationale:**
- The audit log requirement means we need to be able to reconstruct historical state. Hard deletes make this impossible.
- Agent task records reference employees; hard-deleting an employee would require cascade deletes or nullable foreign keys throughout.
- Re-activation of a soft-deleted resource is a common user request. Hard deletes require backup restoration; soft deletes require flipping `deleted_at = NULL`.
- SQLAlchemy event listeners or a custom `Query` subclass can filter `WHERE deleted_at IS NULL` automatically, so callers don't need to remember.

**Trade-offs:** Tables grow indefinitely without a purge strategy. We will implement a configurable hard-purge job (Celery Beat task) that permanently removes records where `deleted_at < NOW() - INTERVAL '90 days'` and the tenant has not opted into longer retention.
