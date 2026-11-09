# Development Plan

## Overview

Six sequential phases from platform foundation to a fully operational business loop. Each phase produces a deployable increment. External dependencies (real API credentials, WeChat account) are isolated to later phases so development can proceed with mocks.

2026-11-09 增补：公开首页、企业发现搜索与轻量RAG的当前规划见本文末尾。原有六阶段为历史计划，不据此判断当前功能是否已完成。新增规划均待开发验收；首页搜索以本次确认方案为准。

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

---

## GEO公开首页与轻量检索开发计划

确认日期：2026-11-09。状态：规划已确认，待实施；本次记录计划及保存最新代码，不代表相关功能已开发、部署。结合 `docs/geo_product_spec.md` 第二十一章执行；本节补充此前官网规划中的搜索入口和轻量RAG方案。

### 产品定位与首页布局

营火AI的主要客户仍为小企业主。公开首页展示产品价值、真实产出和企业入驻入口，同时提供“发现企业与服务”站内搜索。搜索既让老板直观看到入驻成果，也允许潜在客户发现企业；不以建设消费者社区为首期目标。

首页从上到下展示：营火AI品牌及AI运营平台定位、开始使用与登录入口；支持企业名称和自然语言需求的站内搜索；经授权的真实企业主页示例；数字员工制作的视频和图文等成果；有证据的效果报告；服务范围、价格及信任信息。保留Always on, Always Growing标语，复杂操作教程放入工作台，不占据首页主要位置。

所有搜索区域及结果明确标注“营火站内搜索”。企业入驻后可从工作台“查看入驻成果”打开主页、搜索企业名或试搜与真实服务相关的需求，再查看站内表现与外部数据。站内搜到仅证明营火内可发现，不证明外部模型推荐；相关需求不保证该企业必然出现或排第一。

| 页面或入口 | 首期职责 | 开放条件 |
| --- | --- | --- |
| `/` | 产品说明、站内搜索、主页示例与企业入驻 | 核心正文公开可读取，规划功能与已上线功能分开 |
| `/search?q=…` | 分页企业结果、筛选、匹配理由与主页链接 | 空结果和异常明确展示，不生成虚构企业 |
| `/shop/{public_slug}` | 已发布企业主页与联系入口 | 按既定首次发布锁定、公开权限及版本规则执行 |
| `/business` | 详细产品能力、服务范围与价格 | 可与首页共用内容，避免重复低质量页面 |
| `/dashboard` | 企业任务、入驻成果及统计 | 保留现有鉴权与工作区隔离 |
| 行业、地区目录 | 辅助发现及站内导航 | 后续根据有效企业数量开放，不铺空目录 |

搜索结果展示企业名称、地区、行业、服务、公开图片、资料更新时间、匹配依据及主页链接。没有明确亲子服务资料时，不能因搜索“亲子酒店”就宣称适合亲子。结果支持地区、行业及服务筛选；自然排序依据相关度与资料可用性，不按付费金额暗中排序，推广需单列标识。只从已发布资料中推荐，不使用模型记忆补充企业。

### 轻量架构与资料存储

复用现有FastAPI、PostgreSQL和任务队列，优先评估pgvector，不为首期重新启用Elasticsearch，也不新增独立向量数据库。部署前验证PostgreSQL版本、扩展安装能力及资源预算；不支持扩展时先提供结构化与关键词搜索，明确语义检索尚未启用。中文全文检索需单独验证分词与索引方案，不能把默认英文配置视为已支持中文。

企业公开资料、地点、服务及已发布快照是事实来源；检索文档及向量仅为可重建的派生索引。按站点、company_id、发布版本、内容条目、来源URL保存文档和分块，记录文本摘要或哈希、向量模型、维度及索引状态。完整公开名称和常用别名独立索引，品牌精确匹配不依赖向量。

索引只读取发布白名单，不读取内部订单、成本、经营目标、凭证或私有素材。发布成功后通过可靠事件或事务发件箱入队构建新版本索引；有状态、重试和定期对账。查询时以当前公开状态及版本再次过滤：索引延迟不能暴露草稿、已撤回内容或旧版服务承诺；必要时回退当前公开资料的关键词检索。旧任务不得覆盖更新版本，重试不得重复建块。

撤回和下架立即使搜索不可见，不能只等待异步删向量。管理员更名仍按稳定企业和站点ID归属，结果链接使用当前规范URL。公共检索与未来企业内部知识问答分离，不能共用无权限边界的资料池。

向量模型独立配置，建议使用 `EMBEDDING_BASE_URL`、`EMBEDDING_MODEL`、`EMBEDDING_API_KEY`，沿用服务器配置及管理员模型管理的安全方式，不写死、不输出密钥。明确接口协议、超时、维度和批次限制。更换模型或维度时后台重建独立索引并校验切换，不能直接比较不兼容向量。只在公开资料变化时批量生成文档向量；查询向量可按规范化请求短期缓存，计入额度与费用。

### 搜索流程与RAG分期

第一步解析企业名、地区、行业和服务需求，优先使用结构化字段及规则；需要时调用模型进行有Schema校验的条件抽取。地区存在歧义时让用户筛选，不由模型断言。所有查询使用参数化数据库访问，不执行模型返回的SQL或任意过滤表达式。

第二步组合结构化筛选、中文关键词和向量召回，融合排名并去重，同一企业默认展示一张卡片。以当前公开资料核对匹配依据，返回分页结果。低相关结果不为填满列表而展示；无匹配明确说明，可建议放宽地区或服务条件，不能悄悄取消用户硬性条件。

第三步为可选RAG回答：先检索，再让现有文本模型根据已返回的公开资料组织说明，关联真实企业ID和可验证引用。结果卡片独立可用，回答生成失败不阻断搜索。没有证据时说明信息不足，不生成“最佳”“保证适合”等无法支持的结论。回答中的企业与URL须属于本次检索结果，外部资料和企业内容作为数据，不作为执行指令。

| 里程碑 | 开发事项 | 可交付结果 |
| --- | --- | --- |
| S0 资料与索引基础 | 公开字段、快照、检索文档、扩展验证、中文检索及模型配置 | 可重建、可追溯、受公开状态约束的索引 |
| S1 首页与混合搜索 | 官网、搜索页、结构化筛选、关键词与语义召回、企业卡片 | 老板可搜到已发布企业，并体验有依据的需求匹配 |
| S2 入驻成果与统计 | 工作台入口、站内搜索事件、企业及管理员报表 | 站内展示、主页点击与联系行为可独立核对 |
| S3 可选RAG回答 | 有依据的总结、引用校验、成本与降级 | 需要时提供自然语言答复，异常仍返回企业结果 |

S0依赖GEO公开资料与发布版本，S1随GEO公开主页首期交付，S2随基础监测一起交付；S3在S1通过真实资料验收后开放，不作为主页可用的阻断条件。首期不强制引入完整RAG框架；文档来源和检索流程变复杂后，再评估按需采用LlamaIndex等组件，不为框架重写业务权限。

### 搜索数据与效果边界

记录search_request_id、搜索时间、筛选条件、结果企业及位置、实际展示事件、企业卡片点击、主页访问和联系入口点击。查询文本可能含个人信息，需限制长度、清理敏感内容、限制访问及保留周期；不把原始查询公开给其他企业。只有实际展示的卡片计为展示，不能把全部候选召回计入曝光。企业试搜、自测、管理员预览与机器人按可识别范围单列或剔除，不能包装为新客户流量。

企业端展示站内搜索展示次数、结果点击、点击率、带来的主页访问及联系行为；管理员端可看平台汇总和分页企业明细、无结果率、检索耗时、索引延迟、向量及回答费用。点击率按同一口径的结果点击除以实际展示计算，无展示时显示暂无数据。跨页与重试按事件ID去重，归因窗口和去重规则明确；无法连接的事件显示未归因。

站内搜索、站外搜索引擎、AI来源访问和外部模型抽样分别统计。营火内的搜索演示不标注为外部收录或外部推荐，也不能将老板本人试搜计入获客成果。官网展示的案例须经授权并附时间、数据来源及口径。

### 开发任务与验收标准

| 编号 | 任务 | 验收标准 |
| --- | --- | --- |
| SEARCH 01 | 公开资料索引及向量配置 | 只索引公开快照；失败可重试；模型切换可重建，密钥无明文泄漏 |
| SEARCH 02 | 发布同步与状态过滤 | 新版成功后可检索；撤回即不可见；索引延迟和旧任务不能返回失效资料 |
| SEARCH 03 | 中文混合检索与分页 | 企业全名可查；地区、行业硬条件有效；同企业不重复；无匹配返回明确空结果 |
| SEARCH 04 | 首页、结果页与入驻成果入口 | 匿名可用，手机可用，直接刷新正常；保留工作台及登录回跳；结果均有主页链接 |
| SEARCH 05 | 事件及两端统计 | 有预期值的样本对账一致；实际展示与召回分开；自测与外部效果分开；越权查询被拒绝 |
| SEARCH 06 | 可选回答及引用校验 | 回答仅使用召回证据；同名企业不混淆；无效引用被拒绝；模型失败正常展示卡片 |
| SEARCH 07 | 性能、成本及回退 | 索引后台执行；查询限流、缓存和成本上限有效；上线前完成备份和降级演练 |

建立经确认的验收问题集，覆盖企业全名、别名、中文服务表达、地区歧义、同名企业、无结果、事实缺失、撤回及模型接口失败。以“安吉亲子酒店”等需求测试匹配依据，缺少事实的服务不能被当作已确认卖点。测试企业与内容不得在正式站点冒充真实商家。

上线前约定企业和文档规模、并发量及目标延迟，并在接近生产的环境压测：精确名称测试集首条命中率必须100%；需求查询按已标注相关性样本验收召回和排序；分页、缓存失效和索引重建必须通过。实际数值目标与测试证据进入上线记录，不以未经测试的容量或第三方推荐作为交付承诺。

按S0至S3逐步实施，不使用“保存计划”代替功能交付。每个阶段单独记录迁移、开关、检查结果、未接入项与回退步骤；官网只展示当时真正可用的能力。
