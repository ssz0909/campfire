"""Create downstream work in the approval transaction, then execute after commit."""
from app.models.task import OperationTask
from app.models.digital_employee import DigitalEmployee
from app.agent.workflows.operations import ROLE_TYPES
from app.agent.workflows.llm_draft import TRANSITIONS

def create_handoffs(db, parent):
    from app.services.execution_loop import enabled, assert_active, child_params, actions_for
    if enabled(parent):
        assert_active(db, parent)
        parent.output = actions_for(parent, parent.output or {})
    if (parent.input_params or {}).get('auto_handoff', True) is False:
        return []
    allowed = TRANSITIONS.get((parent.output or {}).get('role'), set())
    children = db.query(OperationTask).filter_by(company_id=parent.company_id, parent_task_id=parent.id).all()
    existing = {c.digital_employee_id for c in children}
    created, seen, skipped = [], set(), []
    for action in (parent.output or {}).get('next_actions', [])[:5]:
        role = action.get('role')
        if role not in allowed or role in seen:
            continue
        seen.add(role)
        employee = db.query(DigitalEmployee).filter_by(company_id=parent.company_id,
            role_title=role, is_deleted=False, is_active=True).order_by(DigitalEmployee.created_at).first()
        if not employee or 'company' not in (employee.allowed_data_scopes or []):
            skipped.append({'role': role, 'reason': '岗位未启用或无企业数据权限'})
            continue
        if employee.id in existing:
            continue
        child = OperationTask(company_id=parent.company_id, created_by=parent.created_by,
            parent_task_id=parent.id, digital_employee_id=employee.id, task_type=ROLE_TYPES[role],
            title=action['title'][:255], input_params={'goal': action['goal'], 'auto_handoff': True, **({'target_duration_seconds':parent.input_params['target_duration_seconds']} if (parent.input_params or {}).get('target_duration_seconds') else {})},
            status='pending', progress=0, execution_log=[])
        child.input_params = {**child.input_params, **child_params(parent)}
        if role in ('content_planner', 'video_producer'):
            from app.services.video_director import target_duration
            child.input_params = {**child.input_params, 'target_duration_seconds':target_duration(parent.input_params, (parent.input_params or {}).get('execution_goal') or (parent.input_params or {}).get('goal') or parent.title)}
        period = ((parent.output or {}).get('data_sources', {}).get('hotel') or {}).get('period')
        if period and len(period) == 2:
            child.input_params = {**child.input_params, 'date_from': period[0], 'date_to': period[1]}
        db.add(child); db.flush()
        existing.add(employee.id); created.append(child)
    parent.output = {**(parent.output or {}), 'handoff_task_ids': [str(c.id) for c in children + created],
                     'handoff_skipped': skipped}
    return created

def create_video_handoff(db, task):
    from app.models.video_project import VideoProject
    project = db.query(VideoProject).filter_by(company_id=task.company_id, task_id=task.id, is_deleted=False).first()
    if not project:
        from app.services.asset_selection import select_assets_for_video
        goal=' '.join([task.title,(task.input_params or {}).get('goal',''),(task.output or {}).get('report_markdown','')])
        if 'selected_asset_ids' in (task.output or {}):
            from app.models.asset import Asset
            from app.services.video_service import VideoService
            selected_ids=VideoService(db)._validate_selected_assets(task.company_id,task.output['selected_asset_ids'])
            available=db.query(Asset).filter(Asset.company_id==task.company_id,Asset.id.in_(selected_ids)).all() if selected_ids else []
            by_id={a.id:a for a in available}
            selected=[by_id[asset_id] for asset_id in selected_ids]
        else:
            selected=select_assets_for_video(db,task.company_id,goal)
        from app.services.video_director import validate_plan, fallback_plan, target_duration
        duration = target_duration((task.output or {}).get('video_brief') or task.input_params, goal)
        descriptors = [{'id':str(a.id),'name':a.name, 'description':((a.asset_metadata or {}).get('vision_analysis') or {}).get('visual_description') or a.source_description} for a in selected]
        raw_plan = (task.output or {}).get('video_storyboard')
        try:
            plan = validate_plan(raw_plan, descriptors, duration) if raw_plan else fallback_plan(descriptors, duration)
        except ValueError as exc:
            from fastapi import HTTPException
            raise HTTPException(422,str(exc)) from exc
        project = VideoProject(company_id=task.company_id, created_by=task.created_by,
            digital_employee_id=task.digital_employee_id, task_id=task.id, title=task.title,
            creation_mode='prompt_to_video', marketing_goal=(task.input_params or {}).get('goal'),
            script=(task.output or {}).get('video_script') or (task.output or {}).get('report_markdown'), aspect_ratio='9:16',
            target_duration_seconds=duration, storyboard=plan, project_status='draft')
        from app.models.company import Company
        company = db.query(Company).filter_by(id=task.company_id).first()
        project.product_name = company.name if company else None
        project.selected_asset_ids=[str(a.id) for a in selected]
        if selected:project.reference_asset_id=selected[0].id
        if selected:
            directions=[]
            for index,asset in enumerate(selected,1):
                analysis=(asset.asset_metadata or {}).get('vision_analysis') or {}
                directions.append(f"素材{index}（{asset.category or '其他'}，标签：{'、'.join(asset.tags or [])}）：{analysis.get('visual_description') or asset.source_description or asset.name}")
            project.script=(project.script or '')+'\n\n已绑定并按顺序使用以下企业素材：\n'+'\n'.join(directions)
        db.add(project); db.flush()
    task.output = {**(task.output or {}), 'video_project_id': str(project.id)}
    selected_ids=project.selected_asset_ids or []
    if selected_ids:
        from app.models.asset import Asset
        import uuid
        ids=[uuid.UUID(str(value)) for value in selected_ids]
        selected=db.query(Asset).filter(Asset.company_id==task.company_id,Asset.id.in_(ids)).all()
        descriptors=[{'id':str(asset.id),'name':asset.name,'category':asset.category,'tags':asset.tags or [],
            'description':asset.source_description} for asset in selected]
        task.output={**(task.output or {}),'selected_asset_ids':selected_ids,'selected_assets':descriptors}
    return project
