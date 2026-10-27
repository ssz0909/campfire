import io

from PIL import Image

from app.config import settings
from tests.conftest import auth_headers, create_test_company, create_test_user


def test_uploaded_image_and_thumbnail_are_accessible(client, db, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, 'LOCAL_STORAGE_PATH', str(tmp_path))
    monkeypatch.setattr(settings, 'STORAGE_BACKEND', 'local')
    monkeypatch.setattr(settings, 'TASK_EXECUTION_MODE', 'inline')
    # The preview path should not require a model or a running worker.
    monkeypatch.setattr('app.worker.tasks.asset_tasks.vision_worker.submit', lambda *a: None)
    user = create_test_user(db)
    company = create_test_company(db, user)
    image = io.BytesIO()
    Image.new('RGB', (640, 480), 'blue').save(image, 'PNG')
    response = client.post(
        f'/api/v1/companies/{company.id}/assets/upload',
        headers=auth_headers(user),
        files={'file': ('preview.png', image.getvalue(), 'image/png')},
    )
    assert response.status_code == 201, response.text
    asset = response.json()
    assert asset['processing_status'] == 'ready'
    for field in ('file_url', 'thumbnail_url'):
        assert asset[field].startswith('/files/signed/')
        preview = client.get(asset[field])
        assert preview.status_code == 200
        assert preview.headers['content-type'].startswith('image/')
        Image.open(io.BytesIO(preview.content)).verify()

    # Stored references remain stable; listing signs them again for old uploads.
    listing = client.get(
        f'/api/v1/companies/{company.id}/assets', headers=auth_headers(user)
    )
    assert listing.status_code == 200
    for field in ('file_url', 'thumbnail_url'):
        assert client.get(listing.json()['items'][0][field]).status_code == 200
    assert client.get('/files/signed/invalid-token').status_code == 403

def test_video_project_exposes_generated_thumbnail_and_hotel_copy(client, db, monkeypatch, tmp_path):
    from app.models.asset import Asset
    from app.models.video_project import VideoProject
    from app.services.storage_service import StorageService
    monkeypatch.setattr(settings, 'LOCAL_STORAGE_PATH', str(tmp_path))
    monkeypatch.setattr(settings, 'STORAGE_BACKEND', 'local')
    user = create_test_user(db)
    company = create_test_company(db, user, name='湖畔酒店')
    picture = io.BytesIO(); Image.new('RGB', (160,90), 'blue').save(picture, 'JPEG')
    thumbnail = StorageService('local').upload_file(picture.getvalue(), 'output_thumb.jpg', 'image/jpeg')
    output = Asset(company_id=company.id, uploaded_by=user.id, name='成片', original_filename='output.mp4',
        file_key='output.mp4', asset_type='video', mime_type='video/mp4', file_size_bytes=10,
        processing_status='ready', thumbnail_url=thumbnail)
    db.add(output); db.flush()
    project = VideoProject(company_id=company.id, created_by=user.id, title='内部视频制作任务',
        creation_mode='prompt_to_video', project_status='pending_review', output_asset_id=output.id)
    db.add(project); db.commit()
    base = f'/api/v1/companies/{company.id}/video-projects'
    for response in [client.get(base, headers=auth_headers(user)), client.get(base+f'/{project.id}', headers=auth_headers(user))]:
        assert response.status_code == 200, response.text
        data = response.json()
        data = data['items'][0] if 'items' in data else data
        assert client.get(data['output_thumbnail_url']).status_code == 200
        assert '湖畔酒店' in data['publish_title'] and '湖畔酒店' in data['publish_description']
        assert '内部视频制作任务' not in data['publish_title']
