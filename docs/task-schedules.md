# 定时数字员工任务

在「任务 → 新建任务」选择运营总管或其他数字员工，填写目标，再选择「每天定时执行」或「每周指定日期执行」。前端按北京时间（Asia/Shanghai）配置；API 支持 IANA 时区。保存时创建计划模板，不立即执行。已有任务详情可点击「创建定时计划」复制目标，再设置时间。

计划保存于原任务表的 input_params.schedule，模板状态 scheduled / paused；无需新增数据库表或迁移。每次到期复制为独立 OperationTask，关联 schedule_template_id 与 scheduled_for，复用 dispatch_task、数字员工工作流、审核和运营闭环。子任务引用当次执行任务，不引用计划模板，数据时间按每轮执行时解析；固定写明的日期仍按原目标处理。

任务列表的「定时计划」及计划详情支持暂停、恢复，详情显示下次执行和最近20轮记录。暂停只影响后续调度，已启动任务在各自详情取消。修改时间或目标时暂停旧计划并创建新计划。

后端要求 EXECUTION_AUTOMATION_ENABLED=true，复用 execution_automation 常驻线程，每60秒检查一次，不依赖用户打开网页。PostgreSQL session advisory lock 防止多进程同时调度；每次在事务中推进下一执行时间并创建执行记录，再派发。服务中断后尚未派发的 pending 执行可恢复；已 queued/running 的不盲目重派，以避免重复调用模型。异常需要在执行记录中核对并重试。

停机错过多个时间点只补执行一轮，不逐日堆积。上一轮任务处于 pending/queued/running 时跳过当前时点；等待审核的历史任务不阻止下一日新任务。模型调用慢或自动发布/采集耗时会延后后续扫描，因此这是分钟级尽力调度，不保证秒级触发。

调度前重新检查用户、企业、员工状态及 TASK_EXECUTE 权限，失效时暂停计划。计划启动后依然遵守原有审核、预算和平台登录限制；定时执行不等于免审核发布。

API：POST /companies/{company_id}/tasks 添加 schedule（frequency、time、timezone、weekdays；周一=0）；PUT /companies/{company_id}/tasks/{id}/schedule 的 enabled 控制暂停恢复；GET /companies/{company_id}/tasks?status=schedules 查询模板，schedule_template_id 查询单个计划的执行历史。
