# 定时数字员工任务

在「任务 → 新建任务」选择运营总管或其他数字员工，填写目标，再选择「每天定时执行」或「每周指定日期执行」。前端按北京时间（Asia/Shanghai）配置；API 支持 IANA 时区。保存时创建计划模板，不立即执行。已有任务详情可点击「创建定时计划」复制目标，再设置时间。

计划保存于原任务表的 input_params.schedule，模板状态 scheduled / paused；无需新增数据库表或迁移。每次到期复制为独立 OperationTask，关联 schedule_template_id 与 scheduled_for，复用 dispatch_task、数字员工工作流、审核和运营闭环。子任务引用当次执行任务，不引用计划模板，数据时间按每轮执行时解析；固定写明的日期仍按原目标处理。

任务列表的「定时计划」支持编辑、立刻执行、暂停和恢复；详情显示下次执行和最近20轮记录。编辑可修改员工、标题、说明、目标、每日/每周执行时间、行业模板、视频生成与素材策略、审批策略及矩阵发布账号。修改仅影响后续轮次，保留计划暂停状态和执行历史，重新计算下次执行时间。已生成的任务不会随模板改变。行业选择未改变时保留原行业模板快照。

「立刻执行」按计划当前设置创建独立的一次性任务，跳转到其任务详情，沿用当前审批策略。暂停中的计划也可立刻执行一次，不会恢复计划或改变下次定时时间。该计划已有待派发、排队、执行中、待审批、等待外部处理或等待重试的实例时，拒绝重复启动。手动实例通过 manual_schedule_run 标记，并纳入计划执行历史。暂停只影响后续调度，已启动任务在各自详情取消。

后端要求 EXECUTION_AUTOMATION_ENABLED=true，复用 execution_automation 常驻线程，每60秒检查一次，不依赖用户打开网页。PostgreSQL session advisory lock 防止多进程同时调度；每次在事务中推进下一执行时间并创建执行记录，再派发。服务中断后尚未派发的 pending 执行可恢复；已 queued/running 的不盲目重派，以避免重复调用模型。异常需要在执行记录中核对并重试。

停机错过多个时间点只补执行一轮，不逐日堆积。上一轮任务处于 pending/queued/running 时跳过当前时点；等待审核的历史任务不阻止下一日新任务。模型调用慢或自动发布/采集耗时会延后后续扫描，因此这是分钟级尽力调度，不保证秒级触发。

调度前重新检查用户、企业、员工状态及 TASK_EXECUTE 权限，失效时暂停计划。计划启动后依然遵守原有审核、预算和平台登录限制；定时执行不等于免审核发布。

API：POST /companies/{company_id}/tasks 添加 schedule（frequency、time、timezone、weekdays；周一=0）；PUT /companies/{company_id}/tasks/{id}/schedule 的 enabled 控制暂停恢复；GET /companies/{company_id}/tasks?status=schedules 查询模板，schedule_template_id 查询单个计划的执行历史。

PUT /companies/{company_id}/tasks/{id}/schedule-template 使用任务创建字段修改有效计划，schedule 必填，不接受 parent_task_id；POST /companies/{company_id}/tasks/{id}/run-now 立刻执行，返回 201 和新执行任务。两者要求当前工作区 TASK_EXECUTE 权限；自动执行同时检查审批、视频制作和发布权限。无需数据库迁移。
