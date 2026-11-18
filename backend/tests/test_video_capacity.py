from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from app.services.video_capacity import duration_request, capacity_brief, minimum_images
from app.services.video_director import fallback_plan
from tests.conftest import create_test_user, create_test_company
from tests.test_asset_intelligence import make_asset


@pytest.mark.parametrize('text', ['制作30-45秒视频', '制作30至45秒分镜', '制作30—45秒视频', '30秒到45秒视频'])
def test_duration_range_is_preserved(text):
    assert duration_request({}, text) == {'min_seconds':30,'max_seconds':45,'source':'range'}


def test_shared_capacity_respects_fixed_range_default_and_mode():
    assets = [{'id':str(i)} for i in range(9)]
    brief = capacity_brief(assets, duration_request({}, '30-45秒'))
    assert brief['feasible'] and brief['target_duration_seconds'] == 30
    assert brief['minimum_image_count'] == 9
    assert not capacity_brief(assets, duration_request({'target_duration_seconds':45}))['feasible']
    cost = capacity_brief(assets, duration_request({'target_duration_seconds':45}), 'cost')
    assert cost['feasible'] and cost['minimum_image_count'] == 9
    assert capacity_brief(assets[:6], duration_request())['target_duration_seconds'] == 19
    assert not capacity_brief(assets[:4], duration_request())['feasible']
    assert minimum_images(45) == 14


def test_every_reported_quality_capacity_is_executable():
    for count in range(5,25):
        assets=[{'id':str(i)} for i in range(count)]
        brief=capacity_brief(assets,duration_request({}, '15-60秒'))
        plan=fallback_plan(assets,brief['target_duration_seconds'])
        assert sum(s['duration_seconds'] for s in plan)==pytest.approx(brief['target_duration_seconds'])
        assert len(plan)==len({s['source_asset_id'] for s in plan})


def workflow(db, role, goal, count=9, params=None):
    from app.models.task import OperationTask
    from app.agent.workflows.operations import OperationsWorkflow
    user=create_test_user(db); company=create_test_company(db,user)
    for i in range(count):make_asset(db,company,user,f'产品图片{i}','other',[],'真实产品')
    task=OperationTask(company_id=company.id,created_by=user.id,title='产品视频',
        task_type='marketing_planning' if role=='content_planner' else 'video_generation',
        status='running',input_params={'goal':goal,**(params or {})})
    db.add(task);db.flush()
    result=OperationsWorkflow().run(task,SimpleNamespace(require_company=lambda:company.id),db,Mock())
    return task,result


def test_planner_and_producer_use_same_capacity_and_handoff(db):
    from app.models.digital_employee import DigitalEmployee
    from app.services.task_handoff import create_handoffs
    from app.agent.workflows.operations import OperationsWorkflow
    task,result=workflow(db,'content_planner','制作30-45秒产品视频')
    assert result['video_brief']['target_duration_seconds']==30
    task.output=result;task.status='completed'
    db.add(DigitalEmployee(company_id=task.company_id,created_by=task.created_by,
        name='制作员',role_title='video_producer',allowed_data_scopes=['company'],is_active=True))
    db.flush()
    child,=create_handoffs(db,task)
    assert child.input_params['target_duration_seconds']==30
    assert child.input_params['video_duration_request']['source']=='range'
    output=OperationsWorkflow().run(child,SimpleNamespace(require_company=lambda:task.company_id),db,Mock())
    assert output['video_brief']['target_duration_seconds']==30
    assert len(output['video_storyboard'])==9


def test_fixed_infeasible_planning_blocks_both_handoff_paths(db):
    from app.services.task_handoff import create_handoffs
    from app.services.execution_loop import actions_for
    task,result=workflow(db,'content_planner','制作45秒产品视频',params={'execution_loop':True})
    assert result['video_brief']['feasible'] is False
    assert result['video_brief']['minimum_image_count']==14
    result=actions_for(task,result)
    assert result['next_actions']==[] and result['execution_blocked']
    # Direct handoff must also enforce the block, even for an untrusted action.
    task.output={**result,'next_actions':[{'role':'video_producer','title':'视频','goal':'制作45秒'}]}
    assert create_handoffs(db,task)==[]


def test_legacy_failed_child_recovers_original_range(db):
    from app.models.task import OperationTask
    from app.services.video_capacity import task_duration_request
    task,result=workflow(db,'content_planner','制作30-45秒产品视频')
    task.input_params={'goal':'制作30-45秒产品视频'}
    child=OperationTask(company_id=task.company_id,created_by=task.created_by,parent_task_id=task.id,
        title='视频脚本',task_type='video_generation',status='failed',
        input_params={'goal':'上游交付45秒','execution_goal':task.input_params['goal'],'target_duration_seconds':45})
    db.add(child);db.flush()
    request=task_duration_request(db,child)
    assert request['source']=='range' and request['min_seconds']==30


def test_explicit_fixed_video_is_not_silently_shortened(db):
    with pytest.raises(ValueError,match='至少需要14张'):
        workflow(db,'video_producer','制作45秒产品视频')


def test_planner_model_receives_capacity_and_cannot_handoff_infeasible_video(db, monkeypatch):
    import json
    from unittest.mock import AsyncMock
    from app.config import settings
    from app.agent.workflows.llm_draft import enrich
    task,result=workflow(db,'content_planner','制作45秒产品视频')
    for key,value in [('LLM_BASE_URL','https://relay.test/v1'),('LLM_MODEL','test'),('LLM_API_KEY','test')]:
        monkeypatch.setattr(settings,key,value)
    complete=AsyncMock(return_value={'model':'test','input_tokens':10,'output_tokens':10,
        'content':json.dumps({'sections':[{'title':'方案','content':'需要补充5张图片'}],
            'next_actions':[{'role':'video_producer','title':'视频','goal':'制作45秒'}]})})
    monkeypatch.setattr('app.agent.workflows.llm_draft.OpenAIProvider.complete',complete)
    output=enrich(result,task,Mock(),[])
    assert output['next_actions']==[]
    messages=complete.await_args.args[0]
    assert 'minimum_image_count' in messages[0]['content']
    assert json.loads(messages[1]['content'])['video_brief']['minimum_image_count']==14
