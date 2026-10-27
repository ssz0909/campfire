import uuid
import pytest
from fastapi import HTTPException
from app.models.publishing import PublishJob
from app.services.publishing_service import create_republish
from app.services.video_service import VideoService
from tests.test_execution_loop import setup, ready_project


def test_republish_preserves_original_and_copies_location(db):
    user, company, root = setup(db)
    project = ready_project(db, root)
    VideoService(db).approve_project(company.id, project.id, user.id)
    original = db.query(PublishJob).first()
    original.status = 'published'
    original.provider_post_id = 'original-post'
    original.metrics = {'views': 100}
    original.content_snapshot = {**original.content_snapshot, 'location_name': '安吉雲中溪·汤泉度假酒店'}
    db.commit()
    copy = create_republish(db, company.id, user.id, original.id)
    assert copy.id != original.id and copy.status == 'draft'
    assert copy.asset_id == original.asset_id and copy.title == original.title
    assert copy.content_snapshot['location_name'] == '安吉雲中溪·汤泉度假酒店'
    assert copy.content_snapshot['republished_from_job_id'] == str(original.id)
    assert copy.provider_post_id is None and copy.metrics is None
    assert original.status == 'published' and original.metrics == {'views': 100}
    with pytest.raises(HTTPException) as error:
        create_republish(db, uuid.uuid4(), user.id, original.id)
    assert error.value.status_code == 404
    with pytest.raises(HTTPException) as error:
        create_republish(db, company.id, user.id, copy.id)
    assert error.value.status_code == 409
