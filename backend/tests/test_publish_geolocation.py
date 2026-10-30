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


def test_channels_search_uses_configured_hotel_not_ip_and_preserves_request():
    import json
    from types import SimpleNamespace
    from app.services.publish_location import PublishLocationSettings, resolve_location
    class Context:
        def __init__(self): self.handlers = []
        def set_geolocation(self, value): self.location = value
        def grant_permissions(self, permissions, *, origin): self.origin = origin
        def route(self, pattern, handler): self.handlers.append((pattern, handler))
    context = Context()
    _apply_geolocation(context, 'wechat_channels', {'latitude':30.45, 'longitude':119.55})
    _apply_geolocation(context, 'wechat_channels', {'latitude':30.46, 'longitude':119.56})
    assert len(context.handlers) == 1
    assert context.origin == 'https://channels.weixin.qq.com'
    pattern, handler = context.handlers[0]
    endpoint = 'https://channels.weixin.qq.com/micro/content/cgi-bin/mmfinderassistant-bin/helper/helper_search_location'
    original = {'latitude':0, 'longitude':0, 'query':'hotel', 'baseReq':{'session':'opaque'}, 'page':2}
    received = []
    route = SimpleNamespace(request=SimpleNamespace(url=endpoint+'?_rid=opaque', method='POST', post_data_json=original),
                            continue_=lambda **kwargs: received.append(kwargs))
    handler(route)
    result = json.loads(received.pop()['post_data'])
    assert original['latitude'] == 0
    assert {k:v for k,v in result.items() if k not in ('latitude','longitude')} == {k:v for k,v in original.items() if k not in ('latitude','longitude')}
    restored = resolve_location(PublishLocationSettings(latitude=result['latitude'],longitude=result['longitude'],coordinate_system='gcj02'))
    assert restored['latitude'] == pytest.approx(30.46, abs=1e-6)
    assert restored['longitude'] == pytest.approx(119.56, abs=1e-6)
    for url, method, body in [(endpoint.replace('channels.weixin.qq.com','other.example'),'POST',original),
                               (endpoint.replace('helper_search_location','helper_publish'),'POST',original),
                               (endpoint,'GET',original), (endpoint,'POST',{'query':'hotel'})]:
        route.request = SimpleNamespace(url=url, method=method, post_data_json=body)
        handler(route)
        assert received.pop() == {}
