"""Tenant-scoped, deterministic drafts. No fabricated metrics or external writes."""
from collections import Counter
from datetime import date, timedelta

from app.models.asset import Asset
from app.models.company import Company
from app.models.digital_employee import DigitalEmployee
from app.models.task import OperationTask
from app.models.approval import Approval


ROLE_TYPES = {
    "operations_manager": "business_analysis",
    "content_planner": "marketing_planning",
    "video_producer": "video_generation",
    "data_analyst": "business_analysis",
    "operations_assistant": "daily_report",
}


class OperationsWorkflow:
    def run(self, task, tenant_context, db, runtime):
        from app.connectors.hotel.service import HotelConnectorService
        company_id = tenant_context.require_company()
        company = db.query(Company).filter(Company.id == company_id).one()
        employee = None
        if task.digital_employee_id:
            employee = db.query(DigitalEmployee).filter(
                DigitalEmployee.id == task.digital_employee_id,
                DigitalEmployee.company_id == company_id,
                DigitalEmployee.is_deleted == False,
                DigitalEmployee.is_active == True,
            ).first()
            if employee is None:
                raise ValueError("数字员工已停用或不存在")
            if "company" not in (employee.allowed_data_scopes or []):
                raise ValueError("该员工未获企业数据读取授权，请配置数据范围")
        role = employee.role_title if employee else {
            "marketing_planning": "content_planner", "video_generation": "video_producer",
            "daily_report": "operations_assistant",
        }.get(task.task_type, "operations_manager")
        goal = (task.input_params or {}).get("goal") or task.description or task.title
        from app.agent.tools.hotel_data_scope import analysis_period, ensure_analysis_orders
        left, right = analysis_period(task.input_params or {}, goal)
        start, end = left.isoformat(), right.isoformat()
        hotel = HotelConnectorService(company_id, db)
        config = hotel.get_config()
        coverage = None
        if role == 'data_analyst' and not (task.input_params or {}).get('feedback_publish_job_id'):
            coverage = ensure_analysis_orders(hotel, task, tenant_context, runtime, left, right)
        metrics = hotel.metrics(start, end) if config else None
        assets = db.query(Asset).filter(
            Asset.company_id == company_id, Asset.is_deleted == False,
            Asset.processing_status == "ready", Asset.is_available == True,
        ).order_by(Asset.created_at.desc()).limit(100).all()
        tasks = db.query(OperationTask).filter(OperationTask.company_id == company_id,
                                             OperationTask.id != task.id).all()
        from app.models.publishing import PublishJob
        published = db.query(PublishJob).filter(PublishJob.company_id == company_id, PublishJob.status == "published").all()
        pending = db.query(Approval).filter(Approval.company_id == company_id,
                                           Approval.status == "pending").count()
        runtime._append_log(task, "info", f"已读取企业档案、{start} 至 {end} 酒店指标、可用素材与任务审批汇总")
        task.progress = 60
        sources = {
            "company": {"name": company.name, "industry": company.industry,
                        "target_audience": company.target_audience,
                        "brand_positioning": company.brand_positioning},
            "hotel": {"period": [start, end], "status": "available" if metrics and metrics["total_orders"] else "no_data",
                      "last_sync_at": config.last_sync_at.isoformat() if config and config.last_sync_at else None,
                      "metrics": metrics, 'sync_coverage': coverage},
            "assets": [{"id": str(a.id), "name": a.name, "type": a.asset_type,
                        "category":a.category,"tags":a.tags or [],
                        "visual_description":((a.asset_metadata or {}).get('vision_analysis') or {}).get('visual_description'),
                        "caption":((a.asset_metadata or {}).get('vision_analysis') or {}).get('caption')} for a in assets],
            "tasks_by_status": dict(Counter(t.status for t in tasks)),
            "pending_approvals": pending,
            "published_content": [{"title": j.title, "platform_connection_id": str(j.platform_connection_id), "metrics": j.metrics} for j in published],
        }
        selected_assets=[]
        if role=='video_producer':
            from app.services.asset_selection import select_assets_for_video
            selected_assets=select_assets_for_video(db,company_id,goal)
            from app.services.video_director import target_duration
            video_duration=target_duration(task.input_params, (task.input_params or {}).get('execution_goal') or goal)
            sources['selected_assets']=[{'id':str(a.id),'name':a.name,'category':a.category,'tags':a.tags or [],
                'width':a.width,'height':a.height, 'description':((a.asset_metadata or {}).get('vision_analysis') or {}).get('visual_description') or a.source_description} for a in selected_assets]
        feedback_id = (task.input_params or {}).get('feedback_publish_job_id')
        if feedback_id:
            import uuid
            feedback_job = db.query(PublishJob).filter_by(id=uuid.UUID(str(feedback_id)), company_id=company_id).first()
            if feedback_job:
                sources['feedback'] = {'title':feedback_job.title, 'metrics':feedback_job.metrics,
                    'scope_note':'账号级指标不能用于单条作品归因或ROI计算'}
        gaps = []
        if coverage and not coverage['complete']:
            gaps.extend(coverage['notes'])
            gaps.append('所需订单时间范围尚未完整覆盖，以下结果仅为已同步样本，不能代表完整区间')
        if not published:
            gaps.append("尚无已发布内容的回流数据，无法计算抖音或视频号曝光、互动和转化趋势。")
        if not metrics or not metrics["total_orders"]:
            gaps.append(f"{start} 至 {end} 无已同步酒店订单，无法判断经营表现；请先连接并同步订单。")
        if not company.target_audience:
            gaps.append("企业目标客群未填写，内容中的客群定位需要人工补充。")
        if not assets:
            gaps.append("无已处理完成的可用素材，视频制作前请上传素材并确认版权。")
        metric_lines = []
        if metrics and metrics["total_orders"]:
            metric_lines += [f"统计区间：{start} 至 {end}（订单创建日期口径，仅覆盖已同步数据）",
                             f"订单数：{metrics['total_orders']}；取消订单：{metrics['cancelled_orders']}；有效订单：{metrics['active_orders']}"]
            if metrics.get("revenue") is not None:
                metric_lines.append(f"已同步有效订单实收金额：{metrics['revenue']}；间夜：{metrics['room_nights']}")
            else:
                metric_lines.append(f"订单/住宿金额：{metrics.get('order_amount')}；Web 数据不能视为财务实收收入。")
            metric_lines.append(metrics.get("occupancy_note") or "入住率需结合完整营业日数据复核。")
        else:
            metric_lines.append("酒店经营数据不足，当前不输出营收、入住率或增长结论。")
        audience = company.target_audience or "待确认目标客群"
        positioning = company.brand_positioning or "待补充品牌卖点"
        sections = [{"title": "任务目标", "content": str(goal)}]
        if task.parent_task_id:
            parent = db.query(OperationTask).filter(OperationTask.id == task.parent_task_id,
                OperationTask.company_id == company_id, OperationTask.status == "completed").first()
            if not parent:
                raise ValueError("来源任务尚未完成或不可访问")
            sections.append({"title": "上游任务交付", "content": (parent.output or {}).get("report_markdown", parent.title)[:16000]})
        children = db.query(OperationTask).filter_by(company_id=company_id, parent_task_id=task.id).all()
        sources['child_tasks'] = [{'id':str(t.id),'title':t.title,'status':t.status} for t in children]
        next_actions = []
        if role == "content_planner":
            sections += [
                {"title": "营销主题与客群", "content": f"主题：{goal}\n面向：{audience}\n品牌定位：{positioning}\n渠道建议：企业现有内容渠道，先小范围测试。"},
                {"title": "发布文案草稿", "content": f"标题：在{company.name}，安排一次属于自己的放松时光\n正文：围绕“{goal}”，分享一次真实体验。你最关心住宿环境、出行便利还是服务细节？欢迎留言告诉我们。\n配图：优先选用已授权的真实环境图；房型、价格和权益需发布前核实。"},
                {"title": "三日内容计划", "content": "第1日：环境与场景介绍，记录浏览量。\n第2日：解答一个客群常见问题，记录互动量。\n第3日：展示一条真实服务流程，记录咨询量。\n发布后手动回填各渠道数据，再由数据分析员复盘。"},
            ]
            next_actions = [{"role": "video_producer", "title": "制作营销视频脚本", "goal": f"根据以下已审阅文案及原任务时长要求制作节奏鲜明的结构化分镜脚本：{goal}"}]
        elif role == "video_producer":
            sections += [
                {"title": "视频制作方案", "content": f"目标：{goal}\n受众：{audience}\n规格：竖屏9:16，15至60秒成片，每镜1.5至3.5秒，按叙事选材，模型片段剪取后合成；字幕需人工复核。\n本次交付为视频模型脚本与分镜，审批后调用视频模型生成文件。"},
                {"title": "脚本与分镜", "content": f"每个成片镜头1.5至3.5秒｜以已授权酒店环境图作为首帧｜自然推进或横移，保持主体完整并延续真实光线｜{company.name}酒店环境与入住场景｜结尾引导了解更多、咨询入住。不得虚构酒店设施、房型或价格。"},
                {"title": "素材与制作检查", "content": "\n".join(f"可选素材：{a.name}" for a in assets[:10]) or "请上传环境、房型及服务细节素材；确认授权、价格和字幕后，在视频项目中制作。"},
            ]
            if selected_assets:
                sections.append({'title':'已选素材与镜头顺序','content':'\n'.join(
                    f"镜头{i+1}｜素材ID：{a.id}｜{a.name}｜{'、'.join(a.tags or [])}｜{a.source_description or ''}"
                    for i,a in enumerate(selected_assets))+'\n候选素材可重新排序；按结构化分镜选材与裁切，不要求全部使用，避免相邻重复场景。'})
        elif role == "data_analyst":
            sections += [{"title": "经营数据分析", "content": "\n".join(metric_lines)},
                         {"title": "数据质量与结论边界", "content": "同步订单不是完整经营账本。当前未接入内容曝光、点击、咨询与成交归因数据，无法计算内容转化率或ROI。\n复盘建议：确认同步范围，补充渠道数据后比较同口径的前后周期。"}]
            next_actions = [{"role": "operations_manager", "title": "根据数据制定运营行动", "goal": f"根据数据报告制定运营行动，关注：{goal}"}]
            if feedback_id:
                import json
                sections += [{'title':'平台回流指标', 'content':json.dumps(sources.get('feedback',{}),ensure_ascii=False,default=str)},
                    {'title':'下一轮优化计划', 'content':'本轮仅获得账号级指标，不能计算单条作品ROI。下一轮每次只调整一个变量：先测试开头场景或标题；记录发布前与发布后24/72小时同口径指标，比较浏览与互动变化。若缺少作品明细或前期基线，先补齐后再判断效果。计划经确认后另建新一轮执行任务。'}]
                next_actions=[]
        elif role == "operations_assistant":
            counts = Counter(t.status for t in tasks)
            sections += [{"title": "工作日报", "content": f"报告日期：{end}\n任务总数（不含本任务）：{len(tasks)}\n已完成：{counts['completed']}；运行中：{counts['running']}；失败：{counts['failed']}\n待审批：{pending}。"},
                         {"title": "待办与审批提醒", "content": "\n".join(f"{t.title}：{t.status}" for t in tasks if t.status in {"failed", "waiting_approval", "queued"})[:4000] or "当前无失败或待审批任务。"},
                         {"title": "经营摘要", "content": "\n".join(metric_lines)}]
        else:
            sections += [{"title": "经营概览", "content": "\n".join(metric_lines)},
                         {"title": "运营行动建议", "content": f"围绕“{goal}”执行：\n1. 核对企业定位与客群资料，补齐数据缺口。\n2. 内容策划员输出一份面向{audience}的内容计划。\n3. 视频制作员将审核后的主题转成脚本与分镜。\n4. 数据分析员在数据补齐后复盘订单与内容表现。\n5. 运营助理汇总任务与待审批事项。"}]
            next_actions = [{"role": "content_planner", "title": "制定内容计划", "goal": f"围绕运营目标制定三日内容计划：{goal}"},
                            {"role": "data_analyst", "title": "分析酒店经营数据", "goal": f"分析 {start} 至 {end} 的订单并说明数据边界：{goal}"}]
        if employee:
            sections.append({"title": "岗位执行约束", "content": "\n".join(filter(None, [employee.work_goals, employee.system_instructions] + [str(r) for r in (employee.business_rules or [])]))})
        sections.append({"title": "数据缺口与后续补充", "content": "\n".join(gaps) or "请复核同步时间与素材授权后使用结果。"})
        local_storyboard=[]
        if role=='video_producer' and selected_assets:
            from app.services.video_director import fallback_plan
            local_storyboard=fallback_plan(sources['selected_assets'],video_duration)
            sections.append({'title':'结构化分镜草稿','content':'\n'.join(
                f"镜头{s['shot_number']}｜{s['duration_seconds']:.2f}秒｜{s['purpose']}｜{s['framing']}｜{s['camera_movement']}｜素材{s['source_asset_id']}" for s in local_storyboard) + f'\n按每镜5秒生成，预计{len(local_storyboard)}个模型片段，成片按分镜剪取。'})
            if len(selected_assets)<4:
                sections.append({'title':'素材不足提示','content':'独立场景少于4个，将重复素材并调整景别；建议补充不同场景的清晰照片。'})
        report = "\n\n".join(f"## {s['title']}\n{s['content']}" for s in sections)
        # Forbidden brand words must not leak into a publishable draft via user goals.
        for word in company.marketing_forbidden_words or []:
            if word:
                report = report.replace(str(word), "[禁用词已隐藏]")
                for section in sections:
                    section["content"] = section["content"].replace(str(word), "[禁用词已隐藏]")
        task.tools_used = ["company_profile", "hotel_metrics", "asset_catalog", "task_summary"]
        if coverage and coverage['sync_job_ids']:
            task.tools_used.append('hotel_order_sync')
        task.models_used = []
        task.actual_cost_cents = 0
        if employee:
            from datetime import datetime, timezone
            employee.last_executed_at = datetime.now(timezone.utc)
        return {"title": task.title, "mode": "local_rules", "mode_label": "本地规则草稿（未调用大模型）",
                **({'video_storyboard':local_storyboard,'video_brief': {'target_duration_seconds':video_duration,'aspect_ratio':'9:16'}, 'selected_asset_ids':[str(a.id) for a in selected_assets]} if role=='video_producer' else {}),
                "employee_name": employee.name if employee else "运营工作流", "role": role,
                "sections": sections, "report_markdown": report, "data_sources": sources,
                "data_gaps": gaps, "next_actions": next_actions,
                "delivery": "video_script" if role == "video_producer" else "report",
                "notice": "审批仅确认任务草稿；内容发布和视频渲染需另行操作。"}
