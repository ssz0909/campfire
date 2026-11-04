# 仪表盘与作品数据

仪表盘概览补齐 active_tasks、pending_approvals、videos_this_month、total_cost_this_month_usd、tasks_completed_today。日期按 Asia/Shanghai 计算，本月视频指当月创建且未删除的视频项目；费用来自费用记录，非中转账户余额或账单。接口失败展示错误与 —。

仪表盘与数据分析页新增「任务视频 · 平台播放数据」。统计本企业已确认发布且绑定视频项目的发布记录，包含任务、平台账号、播放、点赞、评论、分享、最近采集时间。按账号与作品 ID 去重；账号概览不当成单作品播放量。空值为未采集，不等于 0；失败保留上一次快照。

`GET /companies/{company_id}/analytics/works` 支持 page、page_size、platform、task_id；总任务过滤包括 execution_root_id 下游。
`POST /companies/{company_id}/analytics/works/sync` 需要发布创建权限，返回 202 并后台处理，每账号五分钟内不重复提交。调度每六小时检查，每 tick 最多一个账号，使用 PostgreSQL 会话锁防止重复采集。

采集通过 HTTP 直接读取已授权账号的 Web 作品接口，不启动浏览器、不触碰上传编辑页。抖音适配 janus work_list；视频号适配 post_list。作品 ID 精确匹配优先，无 ID 时要求列表完成、文案唯一、在创建后的 24 小时内发布，且不能被另一条记录认领。匹配后保存作品 ID 与发布时间，后续按 ID 更新。历史延迟超过窗口或同文案多次发布等不确定情况标记待匹配，禁止随意关联。

平台会话失效、接口结构变化、最多 20 页的采集边界可能导致部分作品待采集。页面展示覆盖数及账号采集状态。视频号需有效登录会话后再做真实数据验收；不会伪造播放量。

同步通过平台身份接口校验实时账号身份，不依赖用户停留的上传编辑页；身份暂未就绪显示“账号身份读取暂不可用”，不会修改账号绑定。视频号接受 HTTP 201 等正常2xx响应，使用已加密保存的真实只读请求配置，递增 `currentPage`，根据 `continueFlag` / `totalCount` 判断完整性（最多20页）。

部分匹配显示“部分作品已采集”，按作品分别标注待匹配原因。完整列表没有历史作品 ID 时不误判成登录失效，不将旧快照覆盖成0。历史发布账号关联若有错误，必须用该企业已验证账号中的唯一作品 ID 和文案核对，备份原记录后修正；不以相似标题猜测归属。

# 无浏览器 Web API 采集

仪表盘“同步平台数据”使用 `web_metrics_api.py` 的 HTTP 客户端，不调用 Playwright、不创建浏览器、不进入登录/发布的浏览器线程。后台自动采集也走相同路径；每个后端进程最多一个 HTTP 账号扫描同时执行。

- 抖音：先查询 `/web/api/media/user/info/` 校验稳定 UID，再查询 `/janus/douyin/creator/pc/work_list`，按 `max_cursor` 翻页。
- 视频号：先请求 `/cgi-bin/mmfinderassistant-bin/auth/auth_data` 校验 `finderUsername`，再请求 `/micro/content/cgi-bin/mmfinderassistant-bin/post/post_list`，按 `currentPage` 翻页。201 也是成功响应。
- 用户登录浏览器只观察上述只读接口，在身份已验证后，把必要请求模板和 Cookie 加密保存到各企业/平台/账号目录的 `metrics-api.enc`，权限 600。不同账号不共享 HTTP 客户端或 Cookie。退出 Web 登录会随账号目录一起删除配置。
- 新账号若缺少视频号接口模板，打开对应网页登录，进入作品管理后检查登录状态即可准备；后台明确显示“需准备接口会话”，不会偷偷启动浏览器回退。
- 每账号至多20页、约90秒扫描预算；重复页或游标不前进立即停止，不能把不完整列表标记为完整。请求不跟随重定向，只允许固定 HTTPS 主机/只读路径，不重放发布、上传或删除接口。
- 失效、限流、身份不匹配、接口结构变化时停止采集并保留既有指标；不把接口错误当成播放量0。接口是平台 Web 私有接口，变更后可能需要更新适配器或重新准备会话。
