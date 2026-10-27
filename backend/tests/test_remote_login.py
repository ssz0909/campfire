from tests.conftest import create_test_user, create_test_company, auth_headers
from app.connectors import web_platform


def test_remote_login_view_requires_company_permission(client, db, monkeypatch):
    owner = create_test_user(db)
    company = create_test_company(db, owner)
    outsider = create_test_user(db, email='outsider@example.com')
    calls = []
    def view(company_id, platform, action=None):
        calls.append((company_id, platform, action))
        return {'image': 'data:image/jpeg;base64,test', 'width': 1440, 'height': 960}
    monkeypatch.setattr(web_platform, 'login_view', view)
    url = f'/api/v1/companies/{company.id}/publishing/douyin/web/view'
    assert client.get(url).status_code == 401
    assert client.get(url, headers=auth_headers(outsider)).status_code == 403
    assert not calls
    response = client.get(url, headers=auth_headers(owner))
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    assert len(calls) == 1
    action_url = url.replace('/view', '/action')
    assert client.post(action_url, headers=auth_headers(owner), json={'kind': 'click', 'x': 2000}).status_code == 422
    assert client.post(action_url, headers=auth_headers(owner), json={'kind': 'navigate', 'url': 'http://localhost'}).status_code == 422
    assert len(calls) == 1
    assert client.post(action_url, headers=auth_headers(owner), json={'kind': 'click', 'x': 120, 'y': 90}).status_code == 200
    assert calls[-1][2]['x'] == 120


def test_remote_login_closed_session_and_unsupported_platform(monkeypatch):
    monkeypatch.setattr(web_platform, '_get_session', lambda *args: None)
    import pytest
    with pytest.raises(RuntimeError):
        web_platform.login_view('company', 'douyin')
    with pytest.raises(ValueError):
        web_platform.login_view('company', 'unknown')


def test_remote_login_text_is_inserted_and_input_focus_returned(monkeypatch):
    from types import SimpleNamespace
    typed = []
    frame = SimpleNamespace(evaluate=lambda script: True)
    page = SimpleNamespace(is_closed=lambda: False, keyboard=SimpleNamespace(insert_text=typed.append),
                           frames=[frame], screenshot=lambda **kwargs: b'image',
                           viewport_size={'width': 1440, 'height': 960})
    monkeypatch.setattr(web_platform, '_get_session', lambda *args: {'page': page})
    result = web_platform.login_view('company', 'douyin', {'kind': 'text', 'text': '123456'})
    assert typed == ['123456']
    assert result['input_focused'] is True
    assert '123456' not in str(result)


def test_fill_targets_selected_field_and_rejects_stale_target(monkeypatch):
    from types import SimpleNamespace
    import pytest
    filled = []
    page = SimpleNamespace(is_closed=lambda: False, frames=[], screenshot=lambda **kwargs: b'image', viewport_size=None)
    session = {'page': page, 'login_input': {'id': 'a'*32, 'locator': SimpleNamespace(fill=lambda text, **kwargs: filled.append(text))}}
    monkeypatch.setattr(web_platform, '_get_session', lambda *args: session)
    web_platform.login_view('company', 'douyin', {'kind': 'fill', 'field_id': 'a'*32, 'text': '123456'})
    assert filled == ['123456']
    with pytest.raises(RuntimeError):
        web_platform.login_view('company', 'douyin', {'kind': 'fill', 'field_id': 'b'*32, 'text': 'wrong'})
    assert filled == ['123456']
