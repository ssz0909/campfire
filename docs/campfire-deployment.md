# 营火AI部署

品牌：营火AI · AI运营平台。宣传语：Always on, Always Growing。

服务器：129.211.64.132；站点：https://campfire.dawoai.com。

- 源码与前端产物：`/opt/campfire/releases/20261026`，`/opt/campfire/current` 指向当前版本。
- Python 3.11：`/opt/campfire/python`；虚拟环境：`/opt/campfire/venv`。
- 后端配置：`/opt/campfire/shared/.env`（权限 600），后端目录使用符号链接。
- 本地存储：`/opt/campfire/shared/storage`；浏览器：`/opt/campfire/shared/browsers`。
- 运行账号与服务：`campfire`；systemd 单进程监听 `127.0.0.1:8018`，避免进程内浏览器会话分散。
- Nginx：`/etc/nginx/conf.d/campfire.conf`，HTTPS 同源代理 `/api/`、`/files/`、`/health`，其他路径使用 SPA 回退。
- 证书由服务器 acme.sh 管理，安装至 `/etc/nginx/ssl/campfire.dawoai.com/`，续期后重载 Nginx。

参考模板见 `deploy/`。服务启动前先准备配置与数据库，并执行 `alembic upgrade head`。完整安装依赖使用 `uv pip install --python /opt/campfire/venv/bin/python .`，项目依赖来自 `backend/pyproject.toml`，不是不存在的 requirements.txt。

检查：`systemctl status campfire`、`journalctl -u campfire -n 100`、`curl https://campfire.dawoai.com/health`。重启：`systemctl restart campfire`。

服务及维护脚本必须设置 `PYTHONPATH=/opt/campfire/current/backend`。虚拟环境中可能存在安装时的旧 `app` 包；仅切换工作目录无法保证位于 `/tmp` 的脚本导入当前源码。执行前通过 `inspect.getfile()` 检查关键工作流路径，禁止从 `site-packages/app` 重试任务。

## 前端发布验收

任务创建页包含矩阵账号、定时/自动审批、视频生成策略和分镜复用策略。生产前端必须从同一份已验证的 Git 源码构建，不能用早期线上 dist 快照再挑文件叠加功能。构建后运行 `python frontend/tests/task-matrix-ui.py`：它启动本地产物，以模拟 API 在桌面与手机视口提交多个抖音/视频号账号，并断言请求携带每个具体账号 ID 和复用策略。测试不创建真实任务。发布包及部署记录应关联同一个 Git commit 和产物校验值；线上切换后再次检查入口 HTML 指向的任务表单 bundle，并确认账号多选文案仍在 bundle 中。

生产 `PUBLIC_BASE_URL` 必须是实际公网 HTTPS 后端地址，使视频模型能读取带签名的参考图；禁止将上传目录公开成无鉴权静态目录。

## 视频行业模板

行业模板存储在 PostgreSQL 的 `industry_templates` 与不可变 `industry_template_versions` 表中，初始迁移提供通用、酒旅及既有行业选项。平台管理员通过 `/admin` 的“行业模板”管理页新增行业、保存草稿、发布、停用和从历史版本还原草稿；普通企业不能编辑平台行业规则。新行业仅需管理后台操作，不需再发版。新增素材识别类别或行业专属业务集成时仍需代码变更。

工作区行业选项由 `GET /api/v1/industries` 返回。新任务按任务行业覆盖、工作区行业、通用兜底的顺序解析模板；`industry_template_snapshot` 由服务端写入任务与视频项目，包含行业、版本、模板内容和通用底座版本。下游、重试及定时轮次沿用该快照。旧企业行业代码 `hotel`、`tourism` 与中文酒店/景区别名解析到 `travel`；未识别的历史行业使用通用模板，不批量改写企业数据。

模板只控制视频创作定位、选材提示、术语和文案风格；通用底座保留任务与事实优先规则、时长/分镜约束、默认关注咨询、生成/剪辑及发布控制。模板关键词仅作同等相关素材的排序提示。`POST /api/v1/admin/industry-templates/{code}/publish` 会保存不可变版本；修改草稿不会影响线上任务。管理员操作写入 audit log，通用模板不能停用。

远程服务器不显示用户本机 Chrome 窗口。平台发布页现提供公司权限隔离的云端登录画面，每 4 秒更新，支持扫码、点击、输入、拖动和刷新。截图接口禁止缓存；不返回 Cookie 或任意导航接口。收起画面不会关闭会话。必须由用户完成扫码，不能将浏览器启动当成已授权，平台登录及实际发布仍需真实账号验收。

云端画面的手势阈值使用本机显示像素，避免画面缩小后把正常点击误判为拖动；坐标按接口返回的视口尺寸换算。手势及待处理操作期间不应用旧轮询画面，文字填入和后续点击保持顺序。被验证弹窗遮挡的输入框不再生成本地输入层。后端转发用户点击并等待页面绘制，不自动选择验证方式、发送短信或处理人脸验证。回归：`node --test frontend/tests/remote-login-pointer.test.cjs`；前端构建后使用安装了 Playwright 的 Python 执行 `frontend/tests/remote-login-ui.py`，只调用模拟接口，覆盖 1440/390 宽度的轮询、轻微手抖和文字/点击顺序；`backend/tests/test_remote_login_browser.py` 使用本地 iframe 与遮挡控件测试。

抖音 `second_verify_panel` 顶层身份验证组件使用兼容激活路径：对用户点击坐标执行命中检测，只激活该点实际命中的可点击祖先，通过正常 DOM click 冒泡交给平台。普通页面、输入框及拖动继续走原有浏览器输入；禁用控件停止操作；已激活的控件不再补发鼠标点击，避免重复请求。不会按文字自动选择短信或人脸验证，也不会调用平台私有 React 回调。2026-11-03 已由用户实际扫码并确认能够进入验证下一步；验证码与刷脸仍由用户本人完成。

同一企业及发布权限下的 `GET .../publishing/{platform}/web/diagnostics?connection_id=...` 提供只读控件结构、事件类型和最近点击路径，不返回控件文案、输入值、Cookie、完整 URL 或脚本函数源码。接口禁止缓存，可用于区分画面命中与控件激活问题。回归覆盖企业权限隔离、SVG 图标祖先、用户点击的单一验证选项、禁用控件和异常时不重复点击。

已迁移原有账户、酒店、任务、视频项目、上传素材和模型/连接器配置，保留原密码及加密密钥。浏览器登录会话目录未迁移，平台需要重新授权。Chromium 已安装，并以 campfire 服务账号验证无界面启动成功；这仅验证浏览器运行依赖，不代表平台已登录或发布已验收。

备份时同时保存 PostgreSQL campfire 数据库、shared/storage、shared/.env 和 shared/secrets；配置与备份含敏感信息，只允许管理员读取，勿提交到代码仓库。恢复时必须保留原加密密钥。

## GEO主页编辑器发布（2026-11-09）

- 功能源码：`034084402c6684563ac72284b2e090d692da322a`。
- 当前版本：`/opt/campfire/releases/geo-editor-20261109T140531Z`。
- 上一版本：`/opt/campfire/releases/photo-home-20261109T133142Z`。
- 备份：`/opt/campfire/backups/before-geo-editor-20261109T140531Z`，含完整发布目录、数据库逻辑备份、Nginx配置与可执行 `rollback.sh`；不涉及数据库结构迁移。
- 发布前校验249个现网基线源码文件；两次检查发布、视频生成和数字员工执行中的数量均为0。新前端从完整当前源码构建，覆盖产物及功能文件并校验SHA256。
- 验证：GEO、llms、编辑器及浏览器共17项测试通过；任务矩阵与定时任务UI的1440/390宽度回归通过。图片大图与草稿封面预览、条目增删、AI建议放弃、手机布局通过隔离数据库和模拟模型验证，未调用生产付费模型。
- 线上健康正常；公网 `/geo` 入口及新GeoView bundle与本地构建逐字节校验一致；预览、AI整理接口未登录返回401；公开首页与动态llms导航保持可用。

## 企业独立主页与三图风格模板（2026-11-09）

- 功能源码：`1510fc4`；发布目录 `/opt/campfire/releases/geo-style-20261109T145649Z`。
- 备份 `/opt/campfire/backups/before-geo-style-20261109T145649Z` 含完整原发布目录、数据库与Nginx配置，可执行 `rollback.sh` 返回 `/opt/campfire/releases/geo-generic-20261109T142950Z`；本次无需数据库迁移。
- 252个基线源码文件校验一致，切换前两次确认发布/视频/数字员工执行数均为0。企业页切换独立渲染器，官网保持平台壳层；新增经典、画册、海报布局及最多三图配置，管理员可基于注册布局添加模板。
- 19项GEO/llms/编辑器/浏览器用例通过，含三图权限、草稿图片隐私、撤回、管理员布局模板及电脑手机宽度；任务矩阵与定时任务UI回归通过。公网入口和GeoView产物与本地构建SHA256一致，健康检查正常。
