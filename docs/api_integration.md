# API Integration Guide

Configuration and activation requirements for all third-party integrations.

---

## 1. Hotel Connector — 订单来了 (Dingdanlai)

**Status: implemented against the vendor document (`订单来了API.docx`). Verified with
mocked HTTP and the vendor's own sample callback. NOT yet verified against the live
platform** — that needs the credentials listed below.

### What is implemented

| Area | Detail |
|---|---|
| Signing | RSA2 = SHA1withRSA over sorted `appCode,timestamp,version,reqBody` (`app/connectors/hotel/crypto.py`) |
| Client | `/open/platform/api/tp/token`, `/open/pms/third/hotel/fetch`, `/open/pms/hotel/data/listRoomInfos`, `.../order/search`, `.../order/detail` (`client.py`) |
| Callback | `POST /api/v1/callbacks/ddll`: AES-256-CBC decrypt, then RSA verify with the platform public key, 10-minute replay window; handles `TICKET` and `ORDER_CHANGE` |
| Sync | Async job (state in DB): search order numbers (paged) then fetch each order detail; idempotent upsert |
| Privacy | Guest names, phone numbers and ID numbers are removed/masked before storage |
| Metrics | orders, cancel rate, room-nights, revenue, ADR, lead time; occupancy only when room count is known, otherwise `null` + "数据不足" |
| Security | Store token encrypted at rest (Fernet), returned only masked; one store binds to exactly one tenant; all queries tenant-scoped |

### Token flow (implemented per the vendor document)

```
ticket  (pushed to our callback ~every 10 min)
   -> POST /open/platform/api/tp/token       -> componentAccessToken
   -> POST /open/platform/api/tp/auth/token  -> authAccessToken (2h) + authRefreshToken (30d)
```

* The store token is **minted automatically** when missing or within 5 minutes of expiry, and
  re-minted once if a call fails with an expired-token code. Operators only enter the **hotel number**;
  a token can still be pasted manually as a fallback.
* Tokens are Fernet-encrypted at rest; the API only ever returns a masked value.
* `authRefreshToken` is stored but not used: **its refresh endpoint is not in the document**, so
  expiry is handled by minting again through `/tp/auth/token`.
* The `/tp/token` response field is assumed to be `componentAccessToken` (the name the next endpoint
  uses). If the platform names it differently the error lists the fields actually returned.
* No public callback URL yet? A platform admin can record the current ticket manually:
  `POST /api/v1/admin/ddll/ticket {"ticket": "..."}`.

### Live-verification status (honest)

| Check | Result |
|---|---|
| Signing + callback crypto vs vendor sample | verified |
| Token flow, sync, metrics, callbacks | verified with a mocked platform (63 tests) |
| **Live call to open.dingdanll.com** | **fails: `-10 签名错误`** |

The live platform rejects our request signature for appCode `1559616142200725504`. Tested and ruled
out: sorted vs document-example key order, compact vs spaced body, appCode in query. A made-up
appCode returns the same `-10`, so the platform checks the signature first.
**Most likely cause: the public key for `my_pkcs8_private.key` is not the one registered for this
app in the 订单来了 console.** Register the public key from `my_x509_public.key` (Base64 body, no
PEM header) as the application public key, then retry. Nothing else can be verified live until this
passes.

### What is still needed to go live

1. **Register our public key** for the app in the 订单来了 console (see above).
2. A **public HTTPS callback URL** `https://<your-domain>/api/v1/callbacks/ddll`, registered with
   订单来了 (needed to receive tickets and order pushes; or enter the ticket manually as above).
3. The store must have **authorized this application** (otherwise code `70009`).

### Known gaps (the document does not specify these; nothing is guessed)

* The refresh endpoint for `authRefreshToken`.
* The exact `/tp/token` response fields (see above).
* Only the last **90 days** of orders are queryable; older history cannot be backfilled.
* Occupancy needs the room count (from `listRoomInfos`), available after a successful connection test.

### Configuration (`backend/.env`, never committed)

```
DDLL_APP_CODE=            # from 订单来了
DDLL_APP_SECRET=          # from 订单来了
DDLL_PRIVATE_KEY_PATH=../my_pkcs8_private.key
DDLL_PLATFORM_PUBLIC_KEY= # platform public key (Base64)
DDLL_AES_KEY=             # platform AES-256 key (Base64)
CREDENTIAL_ENCRYPTION_KEY= # Fernet key; REQUIRED in production
```

Generate the Fernet key with
`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.

### Endpoints (all under `/api/v1/companies/{id}`)

`GET|POST /connectors/hotel` · `POST /connectors/hotel/test` · `POST /connectors/hotel/sync` ·
`GET /connectors/hotel/sync-jobs` · `GET /connectors/hotel/orders` · `GET /connectors/hotel/rooms` ·
`GET /analytics/orders`

---

## 2. OpenAI / LLM Providers

### OpenAI

Used for: script generation, style extraction from reference videos (GPT-4V), agent LLM backbone.

```
OPENAI_API_KEY=sk-...
```

When `OPENAI_API_KEY` is empty or `USE_MOCK_DATA=true`, all LLM calls return pre-defined mock responses. Mock responses are stored in `app/mocks/llm_responses/` and cover the most common prompt patterns.

**Model selection:** The default model is `gpt-4o`. This is configured in `app/config.py` as `LLM_MODEL`. To use a different model (e.g. `gpt-4o-mini` for cost reduction), set:

```
LLM_MODEL=gpt-4o-mini
```

**Rate limits:** OpenAI's API is subject to rate limits by tier. If you encounter `RateLimitError` under load, enable the built-in retry middleware (`LLM_RETRY_MAX=5`, `LLM_RETRY_BACKOFF=exponential` in config) and consider upgrading your OpenAI tier.

### Other LLM providers

The LLM client is abstracted via LangChain's `ChatOpenAI`-compatible interface. To use Anthropic Claude or Azure OpenAI, set:

```
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
LLM_MODEL=[REDACTED]
```

or

```
LLM_PROVIDER=azure_openai
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=https://...
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o
```

Supported providers are defined in `app/llm/factory.py`.

---

## 3. Video Generation Providers

### Mock provider (default)

When `VIDEO_PROVIDER=mock`, the system generates placeholder MP4 clips locally using FFmpeg. Clips are colored rectangles with a text overlay showing the shot description. No external API call is made. This is the default for development.

### Seedance

Seedance is the primary AI video generation provider.

```
VIDEO_PROVIDER=seedance
SEEDANCE_API_KEY=your_key_here
SEEDANCE_API_BASE_URL=https://api.seedance.ai/v1
```

The Seedance client (`app/video/providers/seedance.py`) calls the text-to-video generation endpoint and polls for completion. Average generation time per shot is 30–120 seconds depending on duration and style complexity.

**Rate limits:** Seedance imposes a concurrent job limit. The Celery `video` queue is configured with `--concurrency=2` by default to stay within limits. Adjust `CELERY_VIDEO_CONCURRENCY` if your Seedance plan allows more concurrent jobs.

**Cost tracking:** Each shot generation request is logged to `VideoGenerationLog` with provider, model, duration_seconds, and estimated_cost. Review this table to monitor spend.

### Adding a new video provider

Implement the `VideoProvider` protocol in `app/video/providers/` and register it in `app/video/providers/__init__.py`. Set `VIDEO_PROVIDER=your_provider_name` in the environment.

---

## 4. WeChat API

Used for: mini program user login, push notifications to staff.

### Required credentials

```
WECHAT_APP_ID=wx...
WECHAT_APP_SECRET=...
```

These are obtained from the WeChat Mini Program admin panel at `mp.weixin.qq.com`.

### Login

The backend calls `https://api.weixin.qq.com/sns/jscode2session` during the login flow. This endpoint is only reachable from servers with a registered App ID. It does not work from `localhost` in production mode.

In development with `USE_MOCK_DATA=true`, the login endpoint bypasses the WeChat API call entirely and returns a test JWT. Set `WECHAT_APP_ID` and `WECHAT_APP_SECRET` to any non-empty string to satisfy config validation in mock mode.

### Notifications (WeChat Template Messages / Subscription Messages)

Push notifications require additional WeChat configuration beyond the App ID and App Secret:

1. A template must be approved in the WeChat Mini Program admin panel under "Capabilities → Subscription Messages"
2. The template ID must be set in config: `WECHAT_NOTIFICATION_TEMPLATE_ID=...`
3. Users must explicitly subscribe to receive messages

The notification client is in `app/integrations/wechat/notifications.py`.

### Mock mode

When `USE_MOCK_DATA=true`, all outbound WeChat API calls are intercepted by a mock client that logs the call and returns a success response. No real WeChat messages are sent.

---

## 5. S3-Compatible Storage

### MinIO (development)

MinIO runs as a Docker service. No configuration change is needed beyond what is in `.env.example`.

```
STORAGE_BACKEND=s3
S3_ENDPOINT_URL=http://minio:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET_NAME=aiops-assets
```

The bucket `aiops-assets` is created automatically on first use if it does not exist (the `StorageClient` calls `create_bucket` with `exist_ok=True` at startup).

To access the MinIO web console during development, open `http://localhost:9001` and log in with `minioadmin` / `minioadmin`.

### AWS S3 (production)

```
STORAGE_BACKEND=s3
S3_ENDPOINT_URL=           # leave empty to use AWS default endpoint
S3_ACCESS_KEY=AKIA...
S3_SECRET_KEY=...
S3_BUCKET_NAME=your-production-bucket
AWS_DEFAULT_REGION=ap-east-1
```

**IAM policy:** The application requires these S3 permissions on the bucket:
- `s3:GetObject`
- `s3:PutObject`
- `s3:DeleteObject`
- `s3:ListBucket`
- `s3:GetBucketLocation`

Create a dedicated IAM user with only these permissions. Do not use root credentials or an overly broad IAM role.

**Presigned URLs:** Video downloads and preview links use S3 presigned URLs with a 1-hour expiry. Users never receive direct S3 credentials.

**Bucket per tenant (recommended for production):** For strong data isolation, create one S3 bucket per tenant organization and set the bucket name in each organization's settings. The `StorageClient` reads the bucket name from the organization configuration, falling back to `S3_BUCKET_NAME`.

### Cloudflare R2 (alternative)

R2 is S3-compatible and has no egress fees, which reduces cost for video delivery.

```
STORAGE_BACKEND=s3
S3_ENDPOINT_URL=https://{account_id}.r2.cloudflarestorage.com
S3_ACCESS_KEY=your_r2_access_key
S3_SECRET_KEY=your_r2_secret_key
S3_BUCKET_NAME=aiops-assets
```

No code changes are needed to switch to R2.
