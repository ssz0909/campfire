"""Finite, tenant-scoped operating loop. Models write content, not transitions."""
import uuid

from fastapi import HTTPException

from app.models.task import OperationTask
from app.models.digital_employee import DigitalEmployee
from app.models.video_project import VideoProject
from app.models.publishing import PublishJob, PlatformConnection
from app.models.approval import Approval

PLATFORMS = {'douyin', 'wechat_channels'}
NEXT = {'operations_manager': 'data_analyst', 'data_analyst': 'content_planner',
        'content_planner': 'video_producer'}
TITLES = {'data_analyst': '补齐订单并分析经营，提出改进计划',
          'content_planner': '根据经营分析制定可执行视频内容方案',
          'video_producer': '根据已审批内容方案制作视频脚本'}


def enabled(task):
    return bool((task.input_params or {}).get('execution_loop'))


def configure(params, goal):
    params = dict(params or {})
    if params.get('execution_loop') is None and '执行' in goal and not any(
            word in goal for word in ('不执行', '不要执行', '暂不执行', '仅分析')):
        params['execution_loop'] = True
    targets = params.get('publish_platforms', [])
    if not isinstance(targets, list) or any(p not in PLATFORMS for p in targets):
        raise HTTPException(422, '发布平台仅支持抖音和视频号')
    params['publish_platforms'] = list(dict.fromkeys(targets))
    return params


def root_task(db, task):
    db.flush()
    root_id = (task.input_params or {}).get('execution_root_id')
    if root_id:
        root = db.query(OperationTask).filter_by(id=uuid.UUID(root_id), company_id=task.company_id).populate_existing().first()
        if not root:
            raise HTTPException(409, '执行总任务不存在')
        return root
    return task


def assert_active(db, task):
    root = root_task(db, task)
    if root.status in ('cancelled', 'failed'):
        raise HTTPException(409, '执行总任务已取消或失败，请先处理总任务')
    return root


def actions_for(task, result):
    if not enabled(task) or (task.input_params or {}).get('feedback_publish_job_id'):
        return result
    coverage = (result.get('data_sources', {}).get('hotel') or {}).get('sync_coverage')
    role = result.get('role')
    blocked = role == 'data_analyst' and (not coverage or not coverage.get('complete'))
    next_role = NEXT.get(role)
    goal = (task.input_params or {}).get('execution_goal') or (task.input_params or {}).get('goal') or task.title
    actions = [] if blocked or not next_role else [{
        'role': next_role, 'title': TITLES[next_role],
        'goal': f'执行总目标：{goal}。基于上游已审批交付完成本岗位工作；事实不足时明确标记，不虚构价格、服务或业绩。'
                '当前只生成本岗位草稿；审批后由工作流自动进入下一阶段，不得要求终止后续流程。',
    }]
    return {**result, 'next_actions': actions, 'execution_blocked':
            '订单范围未完整覆盖，请修复连接器后补同步并重新分析' if blocked else None,
            'notice': '执行闭环：分析→内容方案→视频脚本→生成→成片与文案审核→自动发布→数据回流复盘。成片审核通过后自动发布至已选平台，无需再次审批。'}


def child_params(parent):
    params = parent.input_params or {}
    if not enabled(parent):
        return {}
    return {'execution_loop': True, 'execution_root_id': params.get('execution_root_id', str(parent.id)),
            'execution_goal': params.get('execution_goal', params.get('goal', parent.title)),
            'publish_platforms': params.get('publish_platforms', [])}


def queue_publications(db, project):
    if not project.task_id:
        return []
    task = db.query(OperationTask).filter_by(id=project.task_id, company_id=project.company_id).first()
    if not task or not enabled(task):
        return []
    root = assert_active(db, task)
    if project.review_status != 'approved' or project.project_status != 'completed' or not project.output_asset_id:
        raise HTTPException(409, '成片必须审核通过才能排队发布')
    targets = (root.input_params or {}).get('publish_platforms', [])
    copy = (project.quality_check_result or {}).get('approved_publication') or publication_copy(db, project)
    title, description = copy['title'], copy['description']
    jobs = []
    for platform in targets:
        connection = db.query(PlatformConnection).filter_by(company_id=project.company_id, platform=platform).first()
        if not connection:
            connection = PlatformConnection(company_id=project.company_id, platform=platform, status='disconnected')
            db.add(connection); db.flush()
        key = f'execution:{project.id}:{platform}'
        job = db.query(PublishJob).filter_by(company_id=project.company_id, request_key=key).first()
        if job is None:
            job = PublishJob(company_id=project.company_id, platform_connection_id=connection.id,
                requested_by=task.created_by, task_id=task.id, video_project_id=project.id,
                asset_id=project.output_asset_id, title=title,
                description=description, status='queued', request_key=key,
                content_snapshot={'execution_root_id':str(root.id), 'platform':platform,
                                  'asset_id':str(project.output_asset_id), 'title':title,
                                  'description':description,
                                  'location_name':publication_location(db, project.company_id)})
            db.add(job); db.flush()
        jobs.append(job)
    task.output = {**(task.output or {}), 'publish_job_ids':[str(j.id) for j in jobs]}
    return jobs

def publication_location(db, company_id):
    from app.models.company import Company
    company = db.query(Company).filter_by(id=company_id, is_deleted=False).first()
    value = (company.business_goals or {}).get('publish_location_name') if company else None
    return str(value).strip()[:100] if value else None

def publication_geolocation(db, company_id):
    from app.models.company import Company
    company = db.query(Company).filter_by(id=company_id, is_deleted=False).first()
    return (company.business_goals or {}).get('publish_geolocation') if company else None

def publication_copy(db, project):
    from app.models.company import Company
    company = db.query(Company).filter_by(id=project.company_id).first()
    name = project.product_name or (company.name if company else '酒店')
    task = db.query(OperationTask).filter_by(id=project.task_id, company_id=project.company_id).first() if project.task_id else None
    output = task.output or {} if task else {}
    title = (output.get('publish_title') or f'发现{name}，开启下一次入住体验').strip()[:100]
    description = (output.get('publish_description') or '').strip()
    if not description:
        facts = '；'.join(str(p).strip() for p in [project.video_theme, project.key_selling_points] if p)
        description = f'走进{name}，看看这次入住的酒店环境。{facts}。' if facts else f'走进{name}，看看这次入住的酒店环境。'
        description += project.cta_text or '欢迎关注，咨询房型与入住信息，安排下一次旅程。'
    if name not in description:
        description = f'{name}｜{description}'
    if name not in title:
        title = f'{name}｜{title}'[:100]
    for word in (company.marketing_forbidden_words or []) if company else []:
        if word:
            title = title.replace(str(word), '[禁用词已隐藏]')
            description = description.replace(str(word), '[禁用词已隐藏]')
    return {'title':title[:100], 'description':description[:2000], 'asset_id':str(project.output_asset_id)}

def dispatch_queued_publications(db, project_id=None):
    from app.services.publishing_service import web_publish
    query = db.query(PublishJob).filter_by(status='queued')
    if project_id:
        query = query.filter_by(video_project_id=project_id)
    ids = [(j.company_id, j.id) for j in query.all() if (j.content_snapshot or {}).get('execution_root_id')]
    for company_id, job_id in ids:
        try:
            web_publish(db, company_id, job_id)
        except Exception as exc:
            db.rollback()
            job = db.query(PublishJob).filter_by(id=job_id, company_id=company_id).first()
            if job and job.status == 'queued':
                job.status = 'blocked'
                job.error_message = str(getattr(exc, 'detail', '自动发布失败，请检查平台会话后重试'))
                db.commit()

def publish_approved_project(project_id):
    from app.database import SessionLocal
    with SessionLocal() as db:
        dispatch_queued_publications(db, project_id)


def continue_loop(db, root, platforms):
    if root.parent_task_id:
        raise HTTPException(400, '请在总任务上启动或继续闭环')
    if root.status != 'completed':
        raise HTTPException(409, '先审批总任务报告，再继续执行闭环')
    params = configure({**(root.input_params or {}), 'execution_loop':True, 'publish_platforms':platforms}, root.title)
    # Targets cannot silently change after publication requests were created.
    task_ids = [root.id] + [t.id for t in children_for_root(db, root) if enabled(t)]
    related = db.query(VideoProject).filter(VideoProject.company_id==root.company_id, VideoProject.is_deleted==False, VideoProject.task_id.in_(task_ids)).all()
    if any(db.query(PublishJob).filter_by(company_id=root.company_id, video_project_id=p.id).first() for p in related):
        if set(params['publish_platforms']) != set((root.input_params or {}).get('publish_platforms', [])):
            raise HTTPException(409, '已创建发布审批，不能改变目标平台；请另建执行任务')
    root.input_params=params
    db.flush()
    children = db.query(OperationTask).filter_by(company_id=root.company_id,parent_task_id=root.id).all()
    loop_children = [t for t in children if enabled(t)]
    created=[]
    if not loop_children:
        employee=db.query(DigitalEmployee).filter_by(company_id=root.company_id,role_title='data_analyst',is_active=True,is_deleted=False).first()
        if not employee or 'company' not in (employee.allowed_data_scopes or []):
            raise HTTPException(409, '请启用数据分析员并授予企业数据范围')
        from app.agent.tools.hotel_data_scope import analysis_period
        left,right=analysis_period(params,params.get('goal',root.title))
        task=OperationTask(company_id=root.company_id,created_by=root.created_by,parent_task_id=root.id,
            digital_employee_id=employee.id,task_type='business_analysis',title=TITLES['data_analyst'],
            input_params={**child_params(root),'goal':params.get('goal',root.title),
                          'date_from':left.isoformat(),'date_to':right.isoformat()},
            status='pending',progress=0,execution_log=[])
        db.add(task);db.flush();created.append(task)
    else:
        # Repair an approved stage whose dispatch was interrupted, or a former
        # data-gap stage after the connection is fixed. No duplicate sibling.
        from app.services.task_handoff import create_handoffs
        for task in children_for_root(db,root):
            if enabled(task) and task.status == 'completed' and (task.output or {}).get('execution_blocked'):
                task.status='pending';task.output=None;task.progress=0;task.completed_at=None
                task.error_message=None;created.append(task)
                continue
            if enabled(task) and task.status == 'pending':
                created.append(task)
                continue
            if enabled(task) and task.status=='completed' and (task.output or {}).get('role') in NEXT:
                result=actions_for(task,task.output)
                if result.get('execution_blocked'):
                    continue
                task.output=result
                created.extend(create_handoffs(db,task))
    for project in related:
        if project.project_status=='completed' and project.review_status=='approved':
            queue_publications(db,project)
    db.commit()
    return created


def children_for_root(db,root):
    tasks=db.query(OperationTask).filter_by(company_id=root.company_id).all()
    included={root.id}; result=[]
    for _ in range(len(tasks)):
        added=[t for t in tasks if t.id not in included and t.parent_task_id in included]
        if not added: break
        result.extend(added); included.update(t.id for t in added)
    return result


def snapshot(db,task):
    root=root_task(db,task)
    tasks=[root]+[t for t in children_for_root(db,root) if enabled(t)]
    ids=[t.id for t in tasks]
    projects=db.query(VideoProject).filter(VideoProject.company_id==root.company_id,VideoProject.task_id.in_(ids),VideoProject.is_deleted==False).all()
    jobs=db.query(PublishJob).filter(PublishJob.company_id==root.company_id,PublishJob.task_id.in_(ids)).all()
    approvals=db.query(Approval).filter(Approval.company_id==root.company_id,Approval.resource_type=='publish_job',Approval.resource_id.in_([str(j.id) for j in jobs])).all()
    stages=[{'kind':'task','id':str(t.id),'title':t.title,'status':t.status,'role':(t.output or {}).get('role'),
             'error':t.error_message or (t.output or {}).get('execution_blocked') or ('后续岗位未启用或无数据权限，请修复后继续执行' if (t.output or {}).get('handoff_skipped') else None)} for t in tasks]
    stages += [{'kind':'video','id':str(p.id),'title':p.title,'status':p.project_status,
                'error':(p.quality_check_result or {}).get('note')} for p in projects]
    stages += [{'kind':'publish','id':str(j.id),'title':j.title,'status':j.status,'error':j.error_message or (j.metrics or {}).get('feedback_error'),
                'feedback_state':(j.metrics or {}).get('feedback_state'), 'feedback_due_at':(j.metrics or {}).get('feedback_due_at'),
                'platform':(j.content_snapshot or {}).get('platform'),
                'approval_id':next((str(a.id) for a in approvals if a.resource_id==str(j.id) and a.status=='pending'),None)} for j in jobs]
    feedback=[t for t in tasks if (t.input_params or {}).get('feedback_publish_job_id')]
    completed=bool(jobs) and all(j.status=='published' and (j.metrics or {}).get('feedback_task_id') and
        any(str(t.id)==j.metrics['feedback_task_id'] and t.status=='completed' for t in feedback) for j in jobs)
    state='completed' if completed else 'in_progress'
    if root.status=='cancelled': state='cancelled'
    elif root.status=='failed':state='blocked'
    elif any(s.get('error') or s['status'] in ('failed','manual_required','login_required','rejected') for s in stages): state='blocked'
    elif any(s['status'] in ('waiting_approval','pending_review') for s in stages):state='waiting_approval'
    if not enabled(root): state='not_started'
    next_step='查看各阶段状态并处理待审批或失败项'
    if completed:next_step='本轮发布与数据复盘已完成；新一轮优化需另行确认启动'
    elif projects and all(p.project_status=='completed' for p in projects) and not jobs:next_step='在总任务选择目标发布平台并继续执行'
    elif jobs and all(j.status=='published' for j in jobs):next_step='等待发布后定时数据回流与复盘，也可在发布页面手动刷新数据'
    return {'enabled':enabled(root),'root_id':str(root.id),'status':state,'stages':stages,
            'publish_platforms':(root.input_params or {}).get('publish_platforms',[]),'next_step':next_step,
            'notice':'岗位任务完成表示该阶段交付完成；仅发布成功且复盘获批后，本轮闭环才完成。平台账号指标不等于单条作品效果。'}
