from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from app.models.task import OperationTask
from app.schemas.task import TaskCreate, TaskSchedule
from app.schemas.video_project import DefaultMusicSettings, VideoProjectCreate
from app.services.execution_loop import child_params, configure
from app.services.task_service import TaskService
from app.services.video_music import resolve_music_settings, set_default_music
from tests.conftest import create_test_company, create_test_user
from tests.test_asset_intelligence import make_asset


@pytest.mark.parametrize('aspect', ['9:16', '16:9', '1:1'])
def test_aspect_reaches_planning_handoff_and_project(db, aspect):
    from app.agent.workflows.operations import OperationsWorkflow
    from app.models.digital_employee import DigitalEmployee
    from app.services.task_handoff import create_handoffs, create_video_handoff
    from app.services.video_service import VideoService
    user=create_test_user(db);company=create_test_company(db,user)
    for i in range(6):make_asset(db,company,user,f'产品{i}','other',[],'真实产品')
    root=OperationTask(company_id=company.id,created_by=user.id,title='制作15秒产品视频',
        task_type='marketing_planning',status='running',
        input_params={'goal':'制作15秒产品视频','aspect_ratio':aspect})
    employee=DigitalEmployee(company_id=company.id,created_by=user.id,name='制作员',
        role_title='video_producer',allowed_data_scopes=['company'],is_active=True)
    db.add_all([root,employee]);db.flush()
    run=lambda t: OperationsWorkflow().run(t,SimpleNamespace(require_company=lambda:company.id),db,Mock())
    root.output=run(root);root.status='completed'
    assert root.output['video_brief']['aspect_ratio']==aspect
    child,=create_handoffs(db,root)
    assert child.input_params['aspect_ratio']==aspect
    child.output=run(child)
    assert child.output['video_brief']['aspect_ratio']==aspect
    project=create_video_handoff(db,child)
    assert project.aspect_ratio==aspect
    manual=VideoService(db).create_project(company.id,user.id,VideoProjectCreate(
        title='手动视频',creation_mode='ai_creative',aspect_ratio=aspect))
    assert manual.aspect_ratio==aspect


def test_aspect_validation_and_legacy_default():
    assert child_params(SimpleNamespace(input_params={}))['aspect_ratio']=='9:16'
    with pytest.raises(HTTPException) as exc:configure({'aspect_ratio':'4:3'},'制作视频')
    assert exc.value.status_code==422


def test_schedule_aspect_edit_and_immediate_run(db):
    user=create_test_user(db);company=create_test_company(db,user)
    svc=TaskService(db)
    task=svc.create_task(company.id,user.id,TaskCreate(title='定时视频',task_type='video_generation',
        input_params={'goal':'产品视频','aspect_ratio':'9:16'},schedule=TaskSchedule(time='09:00')))
    svc.update_schedule(company.id,task.id,user.id,TaskCreate(title='横屏定时视频',task_type='video_generation',
        input_params={'goal':'产品视频','aspect_ratio':'16:9'},schedule=TaskSchedule(time='10:00')))
    run=svc.run_schedule_now(company.id,task.id,user.id)
    assert run.input_params['aspect_ratio']=='16:9'


def test_selection_prefers_matching_orientation(db):
    from app.services.asset_selection import select_assets_for_video
    user=create_test_user(db);company=create_test_company(db,user)
    wide=make_asset(db,company,user,'横图','other',[],'产品')
    tall=make_asset(db,company,user,'竖图','other',[],'产品')
    wide.width,wide.height=1280,720
    tall.width,tall.height=720,1280
    db.flush()
    for aspect,expected in [('16:9',wide),('9:16',tall)]:
        selected=select_assets_for_video(db,company.id,'产品',limit=1,aspect_ratio=aspect)
        assert selected[0].id==expected.id


def test_workspace_model_audio_clears_stale_music_and_tasks_can_override(db):
    from tests.test_video_music import audio_asset
    user=create_test_user(db);company=create_test_company(db,user)
    music=audio_asset(db,company,user)
    set_default_music(db,company.id,DefaultMusicSettings(selection_mode='fixed',music_asset_id=music.id))
    set_default_music(db,company.id,DefaultMusicSettings(selection_mode='model',music_asset_id=music.id,music_disabled=True))
    saved=company.business_goals['default_video_music']
    assert saved['selection_mode']=='model' and saved['music_asset_id'] is None and saved['music_disabled'] is False
    resolved=resolve_music_settings(db,company.id,{'video_music':{'selection_mode':'workspace'}})
    assert resolved['music_asset_id'] is None and resolved['music_disabled'] is False
    assert resolve_music_settings(db,company.id,{'video_music':{'selection_mode':'none'}})['music_disabled']
    assert resolve_music_settings(db,company.id,{'video_music':{'selection_mode':'fixed','music_asset_id':str(music.id)}})['music_asset_id']==music.id
