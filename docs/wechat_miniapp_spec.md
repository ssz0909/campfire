# WeChat Mini Program Specification

---

## 1. Scope: v1 vs Future

### v1 (Phase 5)

- Staff login via WeChat (wx.login code exchange)
- Task list and task detail view
- Agent status overview (active, paused, error count)
- Receive WeChat notifications for task state changes and review requests
- Basic profile and settings page

### Out of scope for v1 (planned future phases)

- Full video project management (too complex for mobile v1; view-only is acceptable)
- Organization admin functions (onboarding, billing, role management)
- Agent configuration UI
- Analytics dashboards
- Rich media preview (video playback of generated content)
- Multiple language switching (Chinese only in v1)

---

## 2. Authentication Flow

WeChat login follows the server-side code exchange pattern required by WeChat Open Platform. No access token or session key is ever stored on the client beyond the short-lived `code`.

```
Mini Program              Backend                     WeChat Server
     │                      │                               │
     │── wx.login() ────────│                               │
     │◄── code ─────────────│                               │
     │                      │                               │
     │── POST /auth/wechat/login ──────────────────────────►│
     │   {code, tenant_id}  │── GET /sns/jscode2session ───►│
     │                      │◄── {openid, session_key} ─────│
     │                      │                               │
     │                      │── find or create User(openid) │
     │                      │── issue JWT access+refresh ───│
     │◄── {access_token,    │                               │
     │     refresh_token}   │                               │
     │                      │                               │
     │── store tokens in ───│                               │
     │   wx.setStorageSync  │                               │
```

**Key security notes:**
- The `session_key` returned by WeChat is never forwarded to the client. It is held server-side in Redis (TTL: 2 hours) keyed by `openid`.
- If the WeChat code exchange fails (invalid code, network error), the backend returns HTTP 401 with a machine-readable reason. The mini program surfaces a user-facing retry button.
- JWT access tokens expire in 15 minutes. The mini program intercepts 401 responses and attempts a silent refresh using the stored refresh token before retrying the original request.

**First-time login (new user):**
If no `User` record exists for the `openid`, one is created with `is_active=false` and `requires_tenant_binding=true`. The user is redirected to a tenant-binding flow where they enter an invite code or scan a QR code provided by an admin.

---

## 3. Available Features (v1 Page Map)

```
Pages:
├── /pages/login/index          WeChat login entry point
├── /pages/home/index           Dashboard overview (task summary, agent status)
├── /pages/tasks/index          Task list (filterable by state, assignee, agent)
├── /pages/tasks/detail         Task detail, timeline, comments, approve/reject
├── /pages/agents/index         Agent list (name, type, status, last active)
├── /pages/agents/detail        Agent detail (recent tasks, config summary, pause/resume)
├── /pages/notifications/index  Notification history
└── /pages/profile/index        User profile, notification preferences, logout
```

All pages require an authenticated session. Unauthenticated access redirects to `/pages/login/index`.

---

## 4. Technical Requirements

**Framework:** uni-app with Vue 3 Composition API. This enables a single source tree to compile for WeChat Mini Program, Alipay Mini Program, and H5 — reducing maintenance cost for future channel expansion.

**State management:** Pinia (same as the web dashboard; team familiarity is a constraint).

**HTTP client:** `uni.request` wrapped in a typed Axios-like client (`src/utils/request.ts`) that handles JWT refresh and error normalization.

**UI components:** uni-ui or NutUI (both support WeChat Mini Program compilation). Avoid web-only components (native HTML input, anchor tags) in the shared logic layer.

**TypeScript:** Strict mode enabled. All API response types are generated from the OpenAPI schema shared with the web frontend.

**Build tool:** Vite-based uni-app CLI. Mini program compiled output is committed only as a build artifact, not as source.

---

## 5. Configuration Checklist

The following items must be completed before the mini program can authenticate users or call backend APIs. None of these can be mocked for production use.

| Item | Status | Notes |
|---|---|---|
| WeChat Open Platform account registered | Pending | Requires a Chinese business license |
| Mini program created and App ID obtained | Pending | App ID goes into `WECHAT_APP_ID` env var |
| App Secret generated and stored securely | Pending | App Secret goes into `WECHAT_APP_SECRET` env var — never committed |
| Backend domain added to WeChat whitelist | Pending | Production API domain must be HTTPS |
| Request domain whitelist configured | Pending | Add API domain in WeChat Mini Program admin panel under "Development → Development Settings → Server Domain" |
| Upload domain whitelist configured | Pending | Required for file uploads from mini program |
| WebSocket domain whitelist configured | Pending | Required for real-time task updates |
| Download domain whitelist configured | Pending | Required for video preview links from S3/CDN |
| ICP license (备案) for the server domain | Pending | Required for any domain served from mainland China |
| Mini program reviewed and approved by WeChat | Pending | Submit after all credentials are active |

**Important:** WeChat will reject any mini program that calls domains not on the whitelist. Test with the WeChat Developer Tool which enforces the same whitelist rules as production.

---

## 6. Production WeChat Login Requirement

WeChat login cannot be tested or used in production without real credentials. Specifically:

- `wx.login()` only returns a valid `code` in the WeChat app or WeChat Developer Tool — it does not work in a browser.
- The code exchange endpoint (`https://api.weixin.qq.com/sns/jscode2session`) requires a real `WECHAT_APP_ID` and `WECHAT_APP_SECRET`.
- In development, the backend `POST /auth/wechat/login` endpoint is overridden by a mock mode when `USE_MOCK_DATA=true`: it accepts any string as `code` and creates or returns a test user. This mock is disabled when `ENVIRONMENT=production`.
- The mini program itself must be built and submitted through the WeChat Mini Program admin panel. It cannot be accessed as a normal web URL.

If WeChat credentials are not available, the feature branch for Phase 5 can be developed and tested using the WeChat Developer Tool in simulation mode, which satisfies most UI testing requirements but cannot test production payment or sensitive user data flows.
