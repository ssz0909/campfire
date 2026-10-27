from datetime import date
from types import SimpleNamespace

import pytest

from app.agent.tools.hotel_data_scope import analysis_period, missing_windows, ensure_analysis_orders
from app.connectors.hotel.models import HotelConnectorConfig, HotelSyncJob
from app.connectors.hotel.service import HotelConnectorService
from app.core.permissions import Permission
from app.core.tenant_context import TenantContext
from app.models.task import OperationTask
from app.core.secrets import encrypt_json
from tests.conftest import create_test_company, create_test_user


def test_resolve_year_to_date_and_explicit_range():
    today = date(2026, 10, 20)
    assert analysis_period({}, '分析本年度订单', today) == (date(2026, 1, 1), today)
    assert analysis_period({}, '分析去年酒店经营数据', today) == (date(2025, 1, 1), date(2025, 12, 31))
    assert analysis_period({}, '分析2026年3月订单', today) == (date(2026,3,1),date(2026,3,31))
    assert analysis_period({}, '分析2026-01-01至2026-02-28', today) == (date(2026, 1, 1), date(2026, 2, 28))
    assert analysis_period({'date_from':'2026-03-01','date_to':'2026-03-31'}, '本年度', today) == (date(2026,3,1),date(2026,3,31))
    with pytest.raises(ValueError):
        analysis_period({}, '分析近0天', today)
    with pytest.raises(ValueError):
        analysis_period({}, '比较本季度与上季度', today)


def test_successful_job_coverage_not_order_count_drives_missing_windows():
    jobs = [SimpleNamespace(status='success', begin_date='2025-02-01', end_date='2025-02-28'),
            SimpleNamespace(status='partial', begin_date='2025-03-01', end_date='2025-03-31')]
    assert missing_windows(date(2025,1,1), date(2025,3,31),jobs) == [
        (date(2025,1,1),date(2025,1,31)), (date(2025,3,1),date(2025,3,31))]


def setup(db):
    user = create_test_user(db)
    company = create_test_company(db,user)
    config = HotelConnectorConfig(company_id=company.id,hotel_num=123,status='connected',
        encrypted_credentials=encrypt_json({'web_session':{'token':'test'}}))
    task = OperationTask(company_id=company.id,created_by=user.id,title='分析本年度订单',
        task_type='business_analysis',status='running',execution_log=[])
    db.add_all([config,task]);db.commit()
    ctx=TenantContext(user,company.id,{Permission.CONNECTOR_CONFIG})
    runtime=SimpleNamespace(_append_log=lambda *args:None)
    return task,ctx,runtime,HotelConnectorService(company.id,db)


def test_missing_months_sync_before_analysis_and_skip_successful_month(db,monkeypatch):
    task,ctx,runtime,service=setup(db)
    db.add(HotelSyncJob(company_id=task.company_id,status='success',trigger='manual',
        begin_date='2025-02-01',end_date='2025-02-28'));db.commit()
    calls=[]
    async def sync(job):
        calls.append((job.begin_date,job.end_date))
        job.status='success';db.commit();return job
    monkeypatch.setattr(service,'run_sync',sync)
    state=ensure_analysis_orders(service,task,ctx,runtime,date(2025,1,1),date(2025,3,31))
    assert state['complete']
    assert calls==[('2025-01-01','2025-01-31'),('2025-03-01','2025-03-31')]
    assert len(state['sync_job_ids'])==2
    assert ensure_analysis_orders(service,task,ctx,runtime,date(2025,1,1),date(2025,3,31))['sync_job_ids']==[]


def test_permission_required_and_failed_sync_stops_with_gap(db,monkeypatch):
    task,ctx,runtime,service=setup(db)
    ctx.permissions=set()
    state=ensure_analysis_orders(service,task,ctx,runtime,date(2025,1,1),date(2025,3,31))
    assert not state['complete'] and '权限' in state['notes'][0]
    assert db.query(HotelSyncJob).count()==0
    ctx.permissions={Permission.CONNECTOR_CONFIG}
    async def fail(job):
        job.status='failed';job.error='登录过期';db.commit();return job
    monkeypatch.setattr(service,'run_sync',fail)
    state=ensure_analysis_orders(service,task,ctx,runtime,date(2025,1,1),date(2025,3,31))
    assert not state['complete'] and len(state['sync_job_ids'])==1
    assert '登录过期' in state['notes'][0]


def test_open_api_historical_limit_is_not_bypassed(db):
    task,ctx,runtime,service=setup(db)
    service.get_config().encrypted_credentials=encrypt_json({'auth_access_token':'test'})
    db.commit()
    state=ensure_analysis_orders(service,task,ctx,runtime,date(2025,1,1),date(2025,3,31))
    assert not state['complete'] and '90天' in state['notes'][0]
    assert not state['sync_job_ids']


def test_workflow_uses_requested_period_and_records_auto_sync(db,monkeypatch):
    from app.agent.workflows.operations import OperationsWorkflow
    from app.agent.runtime import AgentRuntime
    from app.models.digital_employee import DigitalEmployee
    task,ctx,runtime,service=setup(db)
    employee=DigitalEmployee(company_id=task.company_id,created_by=task.created_by,
        role_title='data_analyst',name='数据分析员',allowed_data_scopes=['company'],is_active=True)
    db.add(employee);db.flush()
    task.digital_employee_id=employee.id
    task.input_params={'goal':'分析2025-01-01至2025-03-31的订单'}
    db.commit()
    calls=[]
    async def sync(self,job):
        calls.append((job.begin_date,job.end_date))
        job.status='success';self.db.commit();return job
    monkeypatch.setattr(HotelConnectorService,'run_sync',sync)
    result=OperationsWorkflow().run(task,ctx,db,AgentRuntime(db))
    assert len(calls)==3
    assert result['data_sources']['hotel']['period']==['2025-01-01','2025-03-31']
    assert result['data_sources']['hotel']['sync_coverage']['complete']
    assert 'hotel_order_sync' in task.tools_used


def test_handoff_preserves_analysis_period(db):
    from tests.test_llm_handoff import setup_parent
    from app.services.task_handoff import create_handoffs
    parent=setup_parent(db)
    parent.output={**parent.output,'data_sources':{'hotel':{'period':['2026-01-01','2026-10-20']}}}
    children=create_handoffs(db,parent)
    assert all(child.input_params['date_from']=='2026-01-01' for child in children)
    assert all(child.input_params['date_to']=='2026-10-20' for child in children)
