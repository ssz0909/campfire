# Open Source License Compliance

Review of planned dependencies for the AI 运营 SaaS platform. All items flagged for legal review are in the "Action Items" section.

---

## License Categories

| Category | License | SaaS implication |
|---|---|---|
| Permissive | MIT, Apache 2.0, BSD 2/3-Clause, ISC | Generally safe for commercial SaaS with attribution |
| Weak copyleft | LGPL 2.1/3.0, MPL 2.0 | Linking is allowed; modifications to the LGPL/MPL-licensed component itself must be released |
| Strong copyleft | GPL 2.0/3.0, AGPL 3.0 | GPL: modifications must be released if distributing; AGPL: modifications must be released if users interact over a network — this is the critical SaaS trigger |
| Commercial / proprietary | Various | Check provider TOS for SaaS use |

---

## Backend Dependencies

| Package | License | Notes |
|---|---|---|
| fastapi | MIT | Safe |
| pydantic | MIT | Safe |
| sqlalchemy | MIT | Safe |
| alembic | MIT | Safe |
| psycopg2-binary | LGPL 3.0 | Linking permitted; binary distribution allowed. No source changes expected. Safe. |
| redis (py) | MIT | Safe |
| celery | BSD 3-Clause | Safe |
| flower | BSD 3-Clause | Safe |
| python-jose | MIT | Safe |
| passlib | BSD 2-Clause | Safe |
| bcrypt | Apache 2.0 | Safe |
| python-multipart | Apache 2.0 | Safe |
| httpx | BSD 3-Clause | Safe |
| boto3 | Apache 2.0 | Safe |
| langchain | MIT | Safe |
| langgraph | MIT | Safe |
| langchain-openai | MIT | Safe |
| openai | MIT | Safe |
| python-magic | MIT | Safe |
| pillow | HPND (MIT-compatible) | Safe |
| uvicorn | BSD 3-Clause | Safe |
| gunicorn | MIT | Safe |
| pytest | MIT | Dev only; not shipped |
| mypy | MIT | Dev only; not shipped |

---

## Frontend Dependencies

| Package | License | Notes |
|---|---|---|
| vue | MIT | Safe |
| vite | MIT | Safe |
| naive-ui | MIT | Safe |
| pinia | MIT | Safe |
| vue-router | MIT | Safe |
| axios | MIT | Safe |
| typescript | Apache 2.0 | Dev only |
| eslint | MIT | Dev only |

---

## Mini Program Dependencies

| Package | License | Notes |
|---|---|---|
| uni-app | Apache 2.0 | Safe |
| @uni-helper/* | MIT | Safe |

---

## Infrastructure

| Component | License | Notes |
|---|---|---|
| PostgreSQL | PostgreSQL License (MIT-compatible) | Safe |
| Redis | BSD 3-Clause | Safe |
| MinIO | AGPL 3.0 | **Flagged — see below** |
| nginx | BSD 2-Clause | Safe |
| FFmpeg | LGPL 2.1+ (core) / GPL 2.0+ (some components) | **Flagged — see below** |

---

## Flagged Items for Legal Review

### MinIO — AGPL 3.0

MinIO's Community Edition is licensed under AGPL 3.0. The AGPL "network use" provision requires that if you run modified AGPL software and allow users to interact with it over a network, you must provide the source of your modifications.

**Key question:** Is this platform modifying MinIO?

If the platform runs an unmodified MinIO instance (the typical case — it's used as a drop-in S3-compatible server), the AGPL's copyleft obligations apply only to MinIO's own source code, not to the application using it. Running unmodified AGPL software as infrastructure is generally considered outside the trigger condition, because you are not distributing a modified version.

**However:** MinIO Inc. themselves are explicit that AGPL means commercial SaaS use requires a commercial license. MinIO's own guidance states: "If you are building a commercial product or service that uses MinIO, you need a commercial license."

**Recommendation:** For the development environment only, MinIO is low-risk. For production, either:
1. Purchase a MinIO commercial license (AIStor), or
2. Replace MinIO with AWS S3 / Google Cloud Storage / Cloudflare R2 — all production-safe S3-compatible options that carry no AGPL obligation.

**Action:** Confirm with legal counsel whether production use of unmodified MinIO AGPL requires a commercial license for this deployment model before public launch.

### FFmpeg — LGPL 2.1+ / GPL considerations

FFmpeg's core libraries (`libavcodec`, `libavformat`, `libavutil`, etc.) are licensed under LGPL 2.1 or later. Dynamically linking LGPL libraries is permitted in commercial software without triggering copyleft, provided the user could relink the application with a modified version of the library.

**Complication:** FFmpeg's build can optionally include GPL-licensed components (certain codecs, encoders). If FFmpeg is compiled with `--enable-gpl`, the entire binary becomes GPL.

The `ffmpeg` package installed via `apt-get` on Debian/Ubuntu is compiled with GPL components enabled.

**Implication:** Running a GPL-binary as a subprocess (as this application does) is generally acceptable for SaaS because you are not distributing the binary to users — you are using it server-side. GPL's distribution trigger does not apply to server-side execution. AGPL is not involved here (FFmpeg is not AGPL).

**Recommendation:** For SaaS server-side use, the GPL binary installed via apt is acceptable. Document this in the legal review. If you ever ship FFmpeg to end users (e.g., in a desktop app), you must use an LGPL-only build or obtain a commercial codec license.

**Action:** Document the FFmpeg usage model (server-side only, not distributed) in the legal review file. Confirm with counsel.

---

## Proprietary / Commercial Provider Terms

| Provider | License | Key SaaS terms |
|---|---|---|
| OpenAI API | Proprietary (TOS) | Commercial use permitted; content generated via API is owned by the user; no use for training competitive models |
| Seedance API | Proprietary (TOS) | Review commercial video generation rights — confirm generated video is licensable for client delivery |
| WeChat Open Platform | Proprietary (TOS) | Mini programs must comply with WeChat platform rules; review data residency requirements for user data |

---

## Action Items

1. **MinIO production use:** Obtain legal opinion on whether production SaaS use of unmodified MinIO AGPL requires a commercial license. If yes, evaluate MinIO AIStor pricing vs switching to AWS S3.

2. **FFmpeg distribution:** Confirm with legal that server-side-only use of a GPL-compiled FFmpeg binary does not create distribution obligations. Document the finding.

3. **Seedance commercial rights:** Review Seedance API TOS specifically for: (a) whether generated video can be sold or delivered to clients, (b) whether there are usage volume limits or per-video licensing fees at scale.

4. **WeChat data residency:** Confirm whether WeChat user data (openid, session data) must be stored in mainland China under Chinese data protection law (PIPL). This may affect database hosting location.

5. **Attribution notices:** Collect all required attribution notices from MIT/Apache/BSD dependencies and include them in a `THIRD_PARTY_LICENSES` file before public release.
