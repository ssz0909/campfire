"""Coordinate regressions; runnable directly without production configuration."""
from app.services.publish_location import PublishLocationSettings, resolve_location, _gcj_offset, baidu_mercator_to_bd09
from fastapi import HTTPException


def test_location_settings():
    for lat, lon in [(30.6, 119.6), (39.9, 116.4)]:
        a, b = _gcj_offset(lat, lon)
        result = resolve_location(PublishLocationSettings(latitude=lat+a, longitude=lon+b))
        assert abs(result['latitude']-lat) < 1e-6
        assert abs(result['longitude']-lon) < 1e-6
    assert resolve_location(PublishLocationSettings()) is None
    for url in ['https://uri.amap.com/marker?position=119.6,30.6',
                'https://api.map.baidu.com/marker?location=30.6,119.6']:
        assert 30 < resolve_location(PublishLocationSettings(map_url=url))['latitude'] < 31

    url = 'https://map.baidu.com/poi/安吉雲中溪·汤泉度假酒店/@13309096.030000001,3541206.7706772247,18.72z?uid=aec125f222eea7255abbbce7\\&da_src=shareurl，'
    # Independent gcoord 1.0.6 reference conversion (BD09MC -> BD09 / WGS84).
    lon, lat = baidu_mercator_to_bd09(13309096.030000001, 3541206.7706772247)
    assert abs(lon-119.55634294592727) < 1e-9
    assert abs(lat-30.461941451726414) < 1e-9
    result = resolve_location(PublishLocationSettings(map_url=url, map_center_confirmed=True))
    assert abs(result['longitude']-119.54496763949915) < 1e-5
    assert abs(result['latitude']-30.458497808278967) < 1e-5
    invalid = [dict(latitude=30), dict(map_url=url),
               dict(map_url='https://map.baidu.com/poi/hotel/@999999999,3541206,18z', map_center_confirmed=True),
               dict(map_url='https://j.map.baidu.com/abc'),
               dict(map_url='https://example.com/?position=119,30')]
    for data in invalid:
        try:
            resolve_location(PublishLocationSettings(**data))
        except HTTPException as exc:
            assert exc.status_code == 422
        else:
            raise AssertionError(data)


if __name__ == '__main__':
    test_location_settings()
    print('Coordinate conversion and Baidu link validation: PASS')
