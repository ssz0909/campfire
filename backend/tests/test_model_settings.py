from app.config import settings
from app.core.security import create_access_token
from app.connectors.hotel.models import PlatformKeyValue
from app.services.model_settings import get_llm_settings, LLM_SETTINGS_KEY
from app.providers.llm.openai_provider import OpenAIProvider
from tests.conftest import create_test_user


def headers(db, admin=True):
    user = create_test_user(db, email=f'{admin}@example.com', is_platform_admin=admin)
    return {'Authorization': 'Bearer ' + create_access_token({'sub': str(user.id)})}


def test_admin_saves_encrypted_settings_and_retains_key(client, db, monkeypatch):
    monkeypatch.setattr(settings, 'LLM_BASE_URL', 'https://env.example/v1')
    monkeypatch.setattr(settings, 'LLM_MODEL', 'env-model')
    monkeypatch.setattr(settings, 'LLM_API_KEY', 'env-secret')
    auth = headers(db)
    response = client.get('/api/v1/admin/model-settings', headers=auth)
    assert response.status_code == 200
    assert response.json()['source'] == 'env'
    assert 'env-secret' not in response.text
    payload = {'base_url': 'https://relay.example/v1/', 'model': 'new-model', 'api_key': 'new-secret'}
    response = client.put('/api/v1/admin/model-settings', headers=auth, json=payload)
    assert response.status_code == 200, response.text
    assert response.json()['source'] == 'database'
    assert 'new-secret' not in response.text
    assert 'new-secret' not in db.get(PlatformKeyValue, LLM_SETTINGS_KEY).encrypted_value
    provider = OpenAIProvider()
    assert (provider._base_url, provider._model, provider._api_key) == (
        'https://relay.example/v1', 'new-model', 'new-secret')
    payload.update(model='changed-model', api_key='')
    response = client.put('/api/v1/admin/model-settings', headers=auth, json=payload)
    assert response.status_code == 200
    assert OpenAIProvider()._model == 'changed-model'
    assert get_llm_settings(db)['api_key'] == 'new-secret'
    assert provider._model == 'new-model'


def test_non_admin_cannot_read_or_write(client, db):
    auth = headers(db, admin=False)
    assert client.get('/api/v1/admin/model-settings', headers=auth).status_code == 403
    assert client.put('/api/v1/admin/model-settings', headers=auth, json={
        'base_url': 'https://relay.example/v1', 'model': 'model', 'api_key': 'key',
    }).status_code == 403


def test_validation_does_not_save_partial_settings(client, db):
    auth = headers(db)
    for values in (
        {'base_url': 'file:///tmp/model', 'model': 'model', 'api_key': 'key'},
        {'base_url': 'https://relay.example/v1?key=secret', 'model': 'model', 'api_key': 'key'},
        {'base_url': 'https://relay.example/v1', 'model': '', 'api_key': 'key'},
        {'base_url': 'https://relay.example/v1', 'model': 'model', 'api_key': ''},
    ):
        assert client.put('/api/v1/admin/model-settings', headers=auth, json=values).status_code == 422
    assert db.get(PlatformKeyValue, LLM_SETTINGS_KEY) is None


def test_video_settings_independent_encrypted_and_used_by_provider(client, db, monkeypatch):
    from app.services.model_settings import get_video_settings, VIDEO_SETTINGS_KEY
    from app.providers.video.relay_provider import RelayVideoProvider
    monkeypatch.setattr(settings, 'VIDEO_BASE_URL', 'https://env.example/v1')
    monkeypatch.setattr(settings, 'VIDEO_MODEL', 'env-video')
    monkeypatch.setattr(settings, 'VIDEO_API_KEY', 'env-video-secret')
    auth = headers(db)
    url = '/api/v1/admin/video-model-settings'
    response = client.get(url, headers=auth)
    assert response.status_code == 200
    assert response.json()['source'] == 'env'
    assert 'env-video-secret' not in response.text
    previous = RelayVideoProvider()
    payload = {'base_url': 'https://relay.example/v1/video/generations/',
               'model': 'wan3.0-video', 'api_key': 'video-secret'}
    response = client.put(url, headers=auth, json=payload)
    assert response.status_code == 200, response.text
    assert response.json()['api_key_configured'] is True
    assert response.json()['source'] == 'database'
    assert 'video-secret' not in response.text
    assert 'video-secret' not in db.get(PlatformKeyValue, VIDEO_SETTINGS_KEY).encrypted_value
    provider = RelayVideoProvider()
    assert (provider.url, provider.model, provider.key) == (
        'https://relay.example/v1/video/generations', 'wan3.0-video', 'video-secret')
    payload.update(base_url='https://other.example/v1', model='updated-video', api_key='')
    assert client.put(url, headers=auth, json=payload).status_code == 200
    assert get_video_settings(db)['api_key'] == 'video-secret'
    assert RelayVideoProvider().url == 'https://other.example/v1/video/generations'
    assert provider.model == 'wan3.0-video'
    assert previous.model == 'env-video'
    assert db.get(PlatformKeyValue, LLM_SETTINGS_KEY) is None


def test_video_settings_permissions_and_validation(client, db):
    from app.services.model_settings import VIDEO_SETTINGS_KEY
    url = '/api/v1/admin/video-model-settings'
    payload = {'base_url': 'https://relay.example/v1', 'model': 'video', 'api_key': 'key'}
    assert client.get(url).status_code == 401
    auth = headers(db, admin=False)
    assert client.get(url, headers=auth).status_code == 403
    assert client.put(url, headers=auth, json=payload).status_code == 403
    auth = headers(db)
    for bad in ({'base_url': 'file:///tmp/model'}, {'base_url': 'https://relay.test?key=secret'},
                {'model': ''}, {'api_key': ''}):
        assert client.put(url, headers=auth, json={**payload, **bad}).status_code == 422
    assert db.get(PlatformKeyValue, VIDEO_SETTINGS_KEY) is None
