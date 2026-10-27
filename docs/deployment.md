# Deployment Guide

---

## Local Development Setup

### Prerequisites

- Docker Desktop (Mac or Windows) or Docker Engine + Docker Compose v2 (Linux)
- Git

No local Python or Node installation is required. All tooling runs inside Docker.

### Step-by-step

**1. Clone the repository**

```bash
git clone <repository-url>
cd AIwork
```

**2. Create your local environment file**

```bash
cp .env.example .env
```

The defaults in `.env.example` work for local development out of the box. You do not need any real API keys to start. Leave `OPENAI_API_KEY`, `SEEDANCE_API_KEY`, and `WECHAT_APP_ID` empty; mock mode covers all functionality.

**3. Start all services**

```bash
docker-compose up
```

Add `-d` to run in the background:

```bash
docker-compose up -d
```

On first run, Docker builds the backend and frontend images. This takes 3–5 minutes. Subsequent starts are fast.

**4. Verify services are healthy**

```bash
docker-compose ps
```

All services should show `healthy` or `running`. The `backend` service starts after `postgres` and `redis` report healthy, which takes about 30 seconds.

**5. Run database migrations**

```bash
docker-compose exec backend alembic upgrade head
```

This applies all migrations and creates the initial schema.

**6. Create a superadmin user** (first time only)

```bash
docker-compose exec backend python -m app.cli create-superadmin \
  --email admin@example.com \
  --password your-local-password \
  --org-name "My Organization"
```

**7. Open the app**

- Web dashboard: http://localhost:5173
- API docs (Swagger): http://localhost:8000/docs
- API docs (Redoc): http://localhost:8000/redoc
- Flower (task monitor): http://localhost:5555
- MinIO console: http://localhost:9001 (user: `minioadmin`, pass: `minioadmin`)

---

## Environment Variable Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | Yes | — | PostgreSQL connection string |
| `REDIS_URL` | Yes | — | Redis connection string (includes auth password) |
| `SECRET_KEY` | Yes | — | JWT signing key; minimum 32 chars; generate with `openssl rand -hex 32` |
| `STORAGE_BACKEND` | Yes | `s3` | `s3` or `local` (local is for tests only) |
| `S3_ENDPOINT_URL` | Yes (s3) | — | Empty for AWS; set to MinIO URL for local |
| `S3_ACCESS_KEY` | Yes (s3) | — | S3 or MinIO access key |
| `S3_SECRET_KEY` | Yes (s3) | — | S3 or MinIO secret key |
| `S3_BUCKET_NAME` | Yes (s3) | — | Bucket name |
| `OPENAI_API_KEY` | No | — | Leave empty to use mock LLM responses |
| `VIDEO_PROVIDER` | No | `mock` | `mock` or `seedance` |
| `SEEDANCE_API_KEY` | No | — | Required when `VIDEO_PROVIDER=seedance` |
| `ENVIRONMENT` | No | `development` | `development` or `production` |
| `USE_MOCK_DATA` | No | `true` | Set `false` when real API keys are active |
| `CORS_ORIGINS` | No | `http://localhost:5173` | Comma-separated allowed origins |
| `WECHAT_APP_ID` | No | — | Required for WeChat mini program login |
| `WECHAT_APP_SECRET` | No | — | Required for WeChat mini program login |
| `FLOWER_BASIC_AUTH` | No | — | `username:password` for Flower in production |
| `SECRET_KEY_PREVIOUS` | No | — | Set during key rotation; remove after one rotation window |

---

## Database Migration Commands

**Apply all pending migrations:**
```bash
docker-compose exec backend alembic upgrade head
```

**Check current migration state:**
```bash
docker-compose exec backend alembic current
```

**Create a new migration after model changes:**
```bash
docker-compose exec backend alembic revision --autogenerate -m "description of change"
```

Review the generated file in `backend/alembic/versions/` before committing. Autogenerate is not perfect — check that destructive operations (column drops, type changes) are intentional.

**Roll back one migration:**
```bash
docker-compose exec backend alembic downgrade -1
```

**Roll back to a specific revision:**
```bash
docker-compose exec backend alembic downgrade <revision_id>
```

---

## Docker Compose Commands

**Start all services:**
```bash
docker-compose up -d
```

**Stop all services (preserve data volumes):**
```bash
docker-compose down
```

**Stop and remove all data volumes (full reset):**
```bash
docker-compose down -v
```

**Restart a single service:**
```bash
docker-compose restart backend
```

**View logs for a service:**
```bash
docker-compose logs -f backend
docker-compose logs -f celery_worker
```

**Open a shell in a running container:**
```bash
docker-compose exec backend bash
docker-compose exec postgres psql -U aiops -d aiops
```

**Rebuild images after dependency changes:**
```bash
docker-compose build --no-cache backend
docker-compose up -d backend celery_worker celery_beat
```

---

## Running Tests

**Backend tests:**
```bash
docker-compose exec backend pytest
```

With coverage:
```bash
docker-compose exec backend pytest --cov=app --cov-report=term-missing
```

A specific test file:
```bash
docker-compose exec backend pytest tests/test_auth.py -v
```

**Frontend tests:**
```bash
docker-compose exec frontend npm run test
```

Type checking:
```bash
docker-compose exec frontend npm run typecheck
```

---

## Production Checklist

Before deploying to a production server, complete every item on this list.

**Environment:**
- [ ] `SECRET_KEY` is a cryptographically random 32+ character string (not the example value)
- [ ] `POSTGRES_PASSWORD` is a strong random password (not `aiops_dev_password`)
- [ ] `REDIS_PASSWORD` is a strong random password (not `aiops_redis_dev`)
- [ ] `MINIO_ROOT_PASSWORD` is changed or MinIO is replaced with AWS S3
- [ ] `ENVIRONMENT=production` is set
- [ ] `USE_MOCK_DATA=false` is set (or omitted — defaults to false when ENVIRONMENT=production)
- [ ] `CORS_ORIGINS` lists only the production frontend domain
- [ ] `FLOWER_BASIC_AUTH` is set and Flower is not publicly accessible

**Infrastructure:**
- [ ] TLS certificate is installed and nginx is configured for HTTPS
- [ ] HTTP redirects to HTTPS (no mixed content)
- [ ] PostgreSQL is not exposed on a public port (no `ports:` mapping in prod compose)
- [ ] Redis is not exposed on a public port
- [ ] MinIO / S3 bucket is private (no public-read ACL)
- [ ] Database backups are configured and tested (see §Backup Strategy)
- [ ] PostgreSQL RLS policies are enabled (`ALTER TABLE ... ENABLE ROW LEVEL SECURITY`)

**Application:**
- [ ] `alembic upgrade head` has been run on the production database
- [ ] A superadmin account has been created via the CLI (not via API)
- [ ] All API integrations needed for Phase 1 are either active or mock mode is documented as intentional
- [ ] Log aggregation is set up (stdout → log shipper)

**Security:**
- [ ] All items in `docs/security.md` §7 cross-tenant test checklist are passing
- [ ] SSL/TLS rating is A or A+ on SSL Labs
- [ ] No secrets in source code (automated scan: `git log --all | grep -i "api_key\|password\|secret"`)

---

## Backup Strategy

**PostgreSQL:**

Use `pg_dump` for logical backups. Run daily at minimum via cron or a Celery Beat task:

```bash
pg_dump -U aiops -h postgres aiops | gzip > backup_$(date +%Y%m%d_%H%M%S).sql.gz
```

Upload to S3:
```bash
aws s3 cp backup_*.sql.gz s3://your-backup-bucket/postgres/
```

Retention: keep 30 daily, 12 monthly backups. Test restore quarterly:
```bash
gunzip -c backup.sql.gz | psql -U aiops -h postgres aiops_restore_test
```

**Redis:**

Redis holds the Celery task queue and JWT session data — these are ephemeral. Redis data loss means in-progress tasks may need to be re-triggered; it does not cause data loss for business records (which are in PostgreSQL). Enable Redis AOF persistence in production (`appendonly yes`) to minimize data loss on restart.

**S3 / MinIO:**

Enable S3 versioning on the production bucket to protect against accidental deletion. Enable cross-region replication for disaster recovery if budget allows.

**Volume snapshots:**

If using Docker volumes on a VM, take nightly VM snapshots or configure block storage snapshots at the cloud provider level. This provides a point-in-time recovery option independent of the application-level backup.
