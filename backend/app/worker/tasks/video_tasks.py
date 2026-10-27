"""Compatibility entry points for persisted Celery messages.

They only resume confirmed provider jobs; new submissions use VideoService.
"""
import uuid
from app.worker.celery_app import celery_app
from app.database import SessionLocal
from app.models.video_project import VideoProject, ProviderTask

def _resume(video_project_id):
    from app.services.video_generation import enqueue
    with SessionLocal() as db:
        project = db.get(VideoProject, uuid.UUID(video_project_id))
        if not project or project.is_deleted:
            return {'status': 'not_found'}
        if project.project_status not in ('analyzing', 'generating_shots', 'compositing', 'waiting_retry'):
            return {'status': project.project_status}
        task = db.query(ProviderTask).filter_by(video_project_id=project.id, company_id=project.company_id).order_by(ProviderTask.created_at.desc()).first()
        if not task or not task.provider_task_id:
            return {'status': 'manual_required', 'message': '历史任务没有确认的模型任务 ID，请核对服务商后台'}
        enqueue(project.id)
        return {'status': 'queued', 'project_id': video_project_id}

@celery_app.task(name='app.worker.tasks.video_tasks.start_video_pipeline')
def start_video_pipeline(video_project_id):
    return _resume(video_project_id)

@celery_app.task(name='app.worker.tasks.video_tasks.poll_provider_tasks')
def poll_provider_tasks(video_project_id):
    return _resume(video_project_id)

@celery_app.task(name='app.worker.tasks.video_tasks.composite_video')
def composite_video(video_project_id):
    return _resume(video_project_id)
