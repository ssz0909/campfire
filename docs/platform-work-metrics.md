# 仪表盘与作品数据

仪表盘概览补齐 active_tasks、pending_approvals、videos_this_month、total_cost_this_month_usd、tasks_completed_today。日期按 Asia/Shanghai 计算，本月视频指当月创建且未删除的视频项目；费用来自费用记录，非中转账户余额或账单。接口失败展示错误与 —。

仪表盘与数据分析页新增「任务视频 · 平台播放数据」。统计本企业已确认发布且绑定视频项目的发布记录，包含任务、平台账号、播放、点赞、评论、分享、最近采集时间。按账号与作品 ID 去重；账号概览不当成单作品播放量。空值为未采集，不等于 0；失败保留上一次快照。

`GET /companies/{company_id}/analytics/works` 支持 page、page_size、platform、task_id；总任务过滤包括 execution_root_id 下游。
`POST /companies/{company_id}/analytics/works/sync` 需要发布创建权限，返回 202 并后台处理，每账号五分钟内不重复提交。调度每六小时检查，每 tick 最多一个账号，使用 PostgreSQL 会话锁防止重复采集。

采集使用独立浏览器标签页访问已授权创作者后台，只读取平台作品列表返回的数据，不触碰上传编辑页。抖音适配 creator item/list、janus work_list；视频号适配 post_list。作品 ID 精确匹配优先，无 ID 时要求列表完成、文案唯一、在创建后的 24 小时内发布，且不能被另一条记录认领。匹配后保存作品 ID 与发布时间，后续按 ID 更新。历史延迟超过窗口或同文案多次发布等不确定情况标记待匹配，禁止随意关联。

平台会话失效、页面结构变化、最多 20 页的采集边界可能导致部分作品待采集。页面展示覆盖数及账号采集状态。视频号需有效登录会话后再做真实数据验收；不会伪造播放量。
