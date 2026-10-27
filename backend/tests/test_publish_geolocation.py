import pytest
from app.connectors.web_platform import _apply_geolocation


def test_geolocation_permission_is_limited_to_platform_origin():
    class Context:
        def set_geolocation(self, value): self.location = value
        def grant_permissions(self, permissions, *, origin): self.permissions, self.origin = permissions, origin
    context = Context()
    _apply_geolocation(context, 'douyin', {'latitude': 30, 'longitude': 119})
    assert context.location == {'latitude': 30.0, 'longitude': 119.0, 'accuracy': 100.0}
    assert context.origin == 'https://creator.douyin.com'
    assert context.permissions == ['geolocation']


@pytest.mark.parametrize('value', [{}, {'latitude':91,'longitude':119}, {'latitude':30,'longitude':181},
    {'latitude':float('nan'),'longitude':119}, {'latitude':True,'longitude':119},
    {'latitude':30,'longitude':119,'accuracy':-1}])
def test_invalid_geolocation_is_rejected_before_browser_access(value):
    with pytest.raises(ValueError):
        _apply_geolocation(None, 'douyin', value)
