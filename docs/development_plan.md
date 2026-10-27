# Development Plan

## Overview

Six sequential phases from platform foundation to a fully operational business loop. Each phase produces a deployable increment. External dependencies (real API credentials, WeChat account) are isolated to later phases so development can proceed with mocks.

---

## Phase 1: Platform Foundation

**Target duration:** 3–4 weeks

### Objectives
Establish the technical substrate that all subsequent features depend on: multi-tenant data model, authentication, role-based access control, database migrations, and the basic web dashboard shell.

### Deliverables

- `Organization` and `User` models with full multi-tenant isolation
- JWT authentication endpoints: register, login, refresh, logout
- RBAC middleware with `owner / admin / manager / staff` roles
- Alembic migration baseline with all Phase 1 tables
- FastAPI app structure: routers, dependency injection, error handling, pagination
- Celery + Beat + Flower wired up and deployable
- MinIO storage client abstraction
- Vue 3 dashboard shell: login page, org switcher, sidebar navigation, user settings
- Docker Compose development environment (all services healthy)
- Basic test suite: auth flows, tenant isolation assertions, RBAC enforcement

### Acceptance Criteria
- A user can register an organization, invite members, assign roles
- Attempting to read another tenant's data returns HTTP 403 — verified by automated test
- All Docker services start healthy with `docker-compose up`
- 80%+ test coverage on auth and tenant isolation code paths

### External Dependencies
None — all functionality runs on local infrastructure with no third-party API keys required.

---

## Phase 2: Agent Runtime and Digital Employees

**Target duration:** 4–5 weeks

### Objectives
Build the LangGraph agent execution engine, define the first two agent types (receptionist and marketing assistant), and expose a management UI for creating and monitoring digital employees.

### Deliverables

- LangGraph checkpoint adapter for PostgreSQL
- `DigitalEmployee` model: type, configuration, assigned tools, status
- Tool registry: base class plus first set of tools (search, notify, create task)
- Agent execution Celery task with retry and human-review gate
- `Task` model with full state machine (PENDING → IN_PROGRESS → AWAITING_REVIEW → COMPLETE / FAILED)
- WebSocket endpoint for real-time task status updates
- Human-in-the-loop review queue in the dashboard
- Receptionist agent: handles order acknowledgment and status queries
- Marketing assistant agent: drafts social media content on request
- Agent management UI: list, create, configure, enable/disable, view task history

### Acceptance Criteria
- An agent can receive a task, execute a multi-step LangGraph workflow, and complete it
- A task that hits the review threshold pauses and appears in the review queue
- Approving a paused task resumes execution from the checkpoint
- Task state updates appear in the dashboard within 2 seconds via WebSocket

### External Dependencies
- OpenAI API key for LLM calls (mock fallback available via `USE_MOCK_DATA=true`)

---

## Phase 3: Video Creation System

**Target duration:** 5–6 weeks

### Objectives
Implement the two-mode video creation pipeline: AI Creative (Mode A) and Reference-Inspired (Mode B). Includes the full shot state machine, FFmpeg synthesis worker, and video project management UI.

### Deliverables

- `VideoProject`, `Shot`, `VideoAsset` models with full state machines
- Mode A pipeline: LLM script generation → shot planning → AI video generation → FFmpeg synthesis
- Mode B pipeline: reference video upload → style extraction → Mode A pipeline continuation
- FFmpeg synthesis worker: concatenation, caption overlay, watermark, audio normalization
- Provider abstraction layer with mock provider and Seedance adapter
- S3 upload/download for all video assets
- Video project management UI: create, view shots, preview, download
- Quality checklist enforcement before project transitions to COMPLETE

### Acceptance Criteria
- End-to-end Mode A video creation completes successfully with mock provider
- FFmpeg synthesis produces a valid MP4 with captions and watermark
- Video project and shot state transitions are atomic and auditable
- Mock mode produces visually distinguishable placeholder clips to confirm pipeline integrity

### External Dependencies
- Seedance API key for real AI video generation (mock available)
- OpenAI API key for script generation (mock available)

---

## Phase 4: Hotel Connector

**Target duration:** 3–4 weeks

### Objectives
Integrate with the hotel order management platform (订单来了 / Dingdanlaile) to enable agents to query and act on real hotel orders.

### Deliverables

- `HotelConnector` model and credential storage (encrypted at rest)
- Dingdanlaile API client: authentication, order query, status update
- Agent tools backed by live hotel data: `search_orders`, `get_order_detail`, `update_order_status`
- Connector health check and status dashboard widget
- Webhook receiver for real-time order events from Dingdanlaile
- Sync job (Celery Beat) for periodic order reconciliation

### Acceptance Criteria
- With real credentials, agents can query live orders and the dashboard reflects accurate data
- Webhook events trigger agent task creation within 5 seconds of receipt
- Connector status widget shows HEALTHY / DEGRADED / DISCONNECTED accurately

### External Dependencies
- Dingdanlaile API credentials and sandbox access (status: PENDING_CREDENTIALS — see `docs/api_integration.md`)

---

## Phase 5: WeChat Mini Program

**Target duration:** 4–5 weeks

### Objectives
Build the staff-facing WeChat mini program for mobile access to task management, agent monitoring, and notifications.

### Deliverables

- uni-app + Vue 3 mini program scaffolding
- WeChat login flow: `wx.login()` → backend `/auth/wechat/login` → JWT
- Task list and detail pages
- Agent status overview
- Push notification binding (WeChat service account or subscription messages)
- Mini program configuration checklist completed (see `docs/wechat_miniapp_spec.md`)

### Acceptance Criteria
- Staff can log in via WeChat and view their assigned tasks
- Task state changes trigger WeChat notifications
- Mini program passes WeChat review checklist

### External Dependencies
- WeChat Open Platform account with real App ID and App Secret
- Registered mini program with domain whitelist configured
- HTTPS endpoint (production or staging) — WeChat requires HTTPS for all API calls

---

## Phase 6: Real Business Operation Loop

**Target duration:** 3–4 weeks (parallel with Phase 5 completion)

### Objectives
Close the loop: real hotel orders arrive, agents process them, videos are created for real, staff manage via WeChat, and the business sees measurable automation.

### Deliverables

- End-to-end integration test with live credentials in staging
- Production Docker Compose deployment with nginx TLS
- Database backup and restore procedure
- Performance baseline: agent task throughput, video pipeline latency
- Operations runbook for common failure modes
- Monitoring: error rate alerts, Celery queue depth alerts

### Acceptance Criteria
- A hotel order arriving via webhook is processed by an agent with zero manual intervention
- A marketing video for a real property is generated and reviewed within the target SLA
- System handles 10 concurrent agent executions without degraded latency
- Production deployment passes the security checklist in `docs/security.md`

### External Dependencies
- All Phase 4 and Phase 5 credentials active
- Production server provisioned with TLS certificate
- SSL/TLS certificate for the production domain
