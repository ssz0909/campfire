from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.connectors.web_platform import _publish_button
from app.schemas.publishing import PublishJobResponse


@pytest.mark.parametrize('status,url,expected', [
    ('manual_required', 'https://creator.douyin.com/creator-micro/content/post/video', None),
    ('published', 'https://creator.douyin.com/creator-micro/content/post/video?enter_from=publish_page', None),
    ('published', 'https://www.douyin.com/video/123456', 'https://www.douyin.com/video/123456'),
])
def test_only_confirmed_content_links_are_exposed(status, url, expected):
    now = datetime.now(timezone.utc)
    job = PublishJobResponse(id=uuid4(), company_id=uuid4(), platform_connection_id=uuid4(),
        requested_by=uuid4(), title='Hotel video', status=status, provider_url=url,
        created_at=now, updated_at=now)
    assert job.model_dump()['provider_url'] == expected


@pytest.mark.parametrize('platform,valid,invalid', [
    ('douyin', ['发布', '立即发布'], ['作品发布', '发布设置', '定时发布', '发布成功']),
    ('wechat_channels', ['发表', '发布', '立即发表'], ['发表设置', '发布成功', '作品发布']),
])
def test_publish_targets_exact_button_labels(platform, valid, invalid):
    class Page:
        def get_by_role(self, role, *, name):
            assert role == 'button'
            return name
    pattern = _publish_button(Page(), platform)
    assert all(pattern.fullmatch(label) for label in valid)
    assert not any(pattern.fullmatch(label) for label in invalid)
