# Security Documentation

---

## 1. Tenant Isolation Implementation

Tenant isolation is enforced at three independent layers. All three must hold simultaneously.

**Application layer (primary enforcement):**
Every repository function that reads or writes data accepts an `organization_id` argument sourced from the authenticated JWT claim. A SQLAlchemy event listener (`TenantQueryFilter`) appends `WHERE organization_id = :oid` to every `SELECT`, `UPDATE`, and `DELETE` on tables that carry the `organization_id` column. The filter is registered on the session factory at startup and cannot be bypassed by calling repository functions directly — the filter is on the session, not on individual functions.

**Database layer (defense-in-depth):**
PostgreSQL row-level security (RLS) policies define an additional access filter. In production, the application database user does not have `BYPASSRLS` privilege. The RLS policy on resource tables is:

```sql
CREATE POLICY tenant_isolation ON resource_table
  USING (organization_id = current_setting('app.current_org_id')::uuid);
```

The application sets `app.current_org_id` at the start of each request via a SQLAlchemy `@event.listens_for(Session, 'after_begin')` hook. RLS is disabled in development (via `ALTER TABLE ... DISABLE ROW LEVEL SECURITY`) to simplify migration testing; it is enabled in production by a post-migration script.

**Validation layer:**
Every inbound request body that references a resource by ID is validated against the organization scope before the database is queried. If a request asks for `resource_id=X` and that resource belongs to a different organization, the lookup returns no results (filtered by the application layer); the handler returns HTTP 404, not 403, to avoid leaking the existence of other tenants' resources.

**Cross-tenant access:**
Only users with `is_superadmin=True` in their JWT can cross tenant boundaries. Superadmin JWTs are issued only by a separate admin CLI command, never by the public login endpoint. The superadmin role check is enforced by a dedicated dependency `require_superadmin()` applied to the small number of routes that require it.

---

## 2. Authentication and Token Strategy

**Password storage:** bcrypt with a work factor of 12. Passwords are never stored in plaintext, never logged, never returned in API responses.

**JWT structure:**

```json
{
  "sub": "<user_uuid>",
  "org": "<organization_uuid>",
  "roles": ["manager"],
  "iss": "aiops-backend",
  "exp": 1234567890,
  "jti": "<unique_token_id>"
}
```

The `jti` (JWT ID) is stored in Redis for the lifetime of the refresh token, enabling revocation. Access tokens are short-lived (15 minutes) and are not stored server-side; they are stateless. Refresh tokens are stored in Redis as `refresh:<jti>` with a 7-day TTL.

**Token revocation:** When a user logs out or an admin deactivates an account, the refresh token `jti` is deleted from Redis. Subsequent refresh attempts return 401. Access tokens issued before revocation remain valid until their 15-minute expiry — this is an accepted trade-off for stateless access tokens. For high-sensitivity operations (password change, account deactivation), the operation timestamp is stored and checked: if the JWT `iat` (issued-at) is before the operation timestamp, the token is rejected.

**WeChat session keys:** WeChat `session_key` values returned during login are stored in Redis (TTL: 2 hours), keyed by `wechat_session:<user_id>`. They are never returned to the client and never written to the database.

**Secret rotation:** The JWT signing key (`SECRET_KEY`) can be rotated with zero downtime by setting `SECRET_KEY_PREVIOUS` during a rolling restart. The middleware attempts verification with `SECRET_KEY` first, then falls back to `SECRET_KEY_PREVIOUS`. After one full rotation window (15 minutes — the access token lifetime), `SECRET_KEY_PREVIOUS` can be removed.

---

## 3. File Upload Security

All file uploads go through a validation pipeline before the file is written to storage.

**Step 1 — Size limit:** Maximum 200MB per upload, enforced by the multipart parser before reading the body. Requests exceeding the limit are rejected with 413 before any file data is processed.

**Step 2 — MIME type validation:** The MIME type is determined using `python-magic`, which reads the file's magic bytes, not the `Content-Type` header. A file claiming to be `image/jpeg` but with PDF magic bytes is rejected. The allowlist is defined per upload type (e.g., video uploads allow `video/mp4`, `video/quicktime`, `video/x-msvideo`; image uploads allow `image/jpeg`, `image/png`, `image/webp`, `image/gif`).

**Step 3 — Storage key:** Files are stored under a UUID key that is generated server-side. User-supplied filenames are stored as metadata but are never used as the storage path. This prevents path traversal and filename injection.

**Step 4 — Virus scanning (optional):** If a ClamAV sidecar is running (`CLAMAV_SOCKET` environment variable is set), the file is scanned before the upload is confirmed. If the scan fails or times out, the upload is rejected. ClamAV is disabled by default because it adds significant startup time to the Docker environment.

**Step 5 — Access control:** Uploaded files are stored with private ACLs. Files are never directly accessible via a public URL. Access is via S3 presigned URLs with a 1-hour expiry, generated only for users who have read access to the resource that references the file.

---

## 4. API Key Storage

Third-party API keys (OpenAI, Seedance, WeChat) are stored exclusively in environment variables. They are:

- Never written to the database in any form.
- Never returned in any API response.
- Never logged (the logging configuration masks values of environment variables matching `*_KEY`, `*_SECRET`, `*_PASSWORD`, `*_TOKEN`).
- Loaded once at application startup into the `Settings` object (Pydantic BaseSettings). The settings object is available via a FastAPI dependency but only exposes the key's presence (boolean), not its value, in any public-facing API response.

For per-tenant API key configuration (e.g., a tenant's own OpenAI key), keys are stored encrypted at rest in the database using AES-256-GCM. The encryption key is derived from `SECRET_KEY` using HKDF. Keys are decrypted in memory only when needed for an API call and are not cached. Encrypted values are never returned in API responses; the API returns only whether a key is configured.

---

## 5. Audit Log Coverage

Every state-mutating API call writes to `audit_log`. The table is append-only: there is no UPDATE or DELETE endpoint for audit records, and the database user does not have `DELETE` permission on `audit_log`.

Covered events:

- User authentication: login, logout, failed login (with IP), password change, token refresh
- User management: create, deactivate, role change, invitation sent/accepted
- Organization management: create, update settings, add/remove member
- Agent management: create, configure, enable, disable, delete
- Task lifecycle: created, started, paused (requires review), approved, rejected, completed, failed
- Video project: created, script approved, synthesis started, completed, failed, deleted
- File uploads: uploaded, deleted
- Integration credentials: configured, updated, removed (key values never logged)
- Superadmin actions: all (additional `is_superadmin=true` flag in the log record)

Each record contains: `id` (UUID), `timestamp` (UTC), `user_id`, `organization_id`, `action` (verb), `resource_type`, `resource_id`, `ip_address`, `user_agent`, `request_id` (correlates with request logs), `result` (success/failure), `details` (JSON, for context that doesn't fit the fixed columns).

---

## 6. Known Limitations and Planned Improvements

| Limitation | Severity | Plan |
|---|---|---|
| RLS disabled in development | Medium | Enable in staging environment before production launch; automated test verifies RLS blocks cross-tenant access |
| Access tokens are stateless (15-min window after revocation) | Low | Acceptable for Phase 1; add a short-lived revocation cache if sensitive operations require it |
| ClamAV scanning is optional and off by default | Low | Enable in production deployment; document in deployment checklist |
| No rate limiting on file upload endpoint | Medium | Add before production; use Redis sliding window same as API rate limiter |
| WeChat session key stored in Redis without encryption at rest | Low | Redis is not exposed externally; add Redis AUTH and encrypt if compliance requires it |
| Audit log has no retention policy | Low | Add configurable retention job (Celery Beat); default 2 years |
| No SIEM integration | Low | Planned: structured log export to a SIEM via a log shipper (Fluent Bit) |

---

## 7. Cross-Tenant Access Test Checklist

These tests must pass before production launch. Run them in the staging environment against the real PostgreSQL instance with RLS enabled.

- [ ] User A in Org 1 cannot read any resource belonging to Org 2 via any `GET` endpoint
- [ ] User A in Org 1 cannot modify any resource belonging to Org 2 via any `PUT`/`PATCH`/`DELETE` endpoint
- [ ] A JWT with `org=org1_id` used against an endpoint that accepts `resource_id=<org2_resource>` returns HTTP 404
- [ ] A crafted request that manually sets `organization_id` in the request body to Org 2's ID is rejected at the validation layer (HTTP 422 or 403, not 200)
- [ ] RLS policy independently blocks cross-tenant access even if the application filter is disabled (verified by direct database session test)
- [ ] A deactivated user's JWT cannot authenticate after logout (refresh token revoked)
- [ ] A password change invalidates tokens issued before the change timestamp
- [ ] Superadmin routes return 403 for non-superadmin tokens
- [ ] Audit log records are created for all events listed in §5
- [ ] Audit log records cannot be deleted or modified via any API endpoint (HTTP 405 or 403)
- [ ] Uploaded files are not accessible without a presigned URL
- [ ] Presigned URLs expire after the configured TTL (default 1 hour)
