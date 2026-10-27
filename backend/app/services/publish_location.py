"""Validate and convert explicitly supplied map coordinates to browser WGS84."""
import math
import re
from urllib.parse import urlparse, parse_qs, unquote
from fastapi import HTTPException
from pydantic import BaseModel, Field
from typing import Literal

class PublishLocationSettings(BaseModel):
    location_name: str = Field(default='', max_length=100)
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    coordinate_system: Literal['wgs84','gcj02','bd09'] = 'gcj02'
    map_url: str = Field(default='', max_length=2000)
    map_center_confirmed: bool = False

def resolve_location(data):
    lat, lon, system = data.latitude, data.longitude, data.coordinate_system
    if data.map_url.strip():
        parsed = urlparse(data.map_url.strip().rstrip('，,。').replace('\\&', '&'))
        host = parsed.hostname or ''
        query = parse_qs(parsed.query)
        if host == 'amap.com' or host.endswith('.amap.com') or host == 'gaode.com' or host.endswith('.gaode.com'):
            value = (query.get('position') or query.get('to') or [''])[0]
            pair = value.split(',')
            if len(pair) >= 2:
                try: lon, lat = float(pair[0]), float(pair[1]); system = 'gcj02'
                except ValueError: raise HTTPException(422, '地图链接坐标格式不正确')
            else: raise HTTPException(422, '该高德链接未包含坐标，请从地图复制经纬度填写；短链接暂不能自动解析')
        elif host in ('map.baidu.com', 'api.map.baidu.com'):
            pair = (query.get('location') or [''])[0].split(',')
            if len(pair) == 2:
                try: lat, lon = map(float, pair); system = 'bd09'
                except ValueError: raise HTTPException(422, '地图链接坐标格式不正确')
            else:
                match = re.search(r'/@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?),', unquote(parsed.path))
                if not match:
                    raise HTTPException(422, '该百度链接没有可解析的坐标；请填写经纬度，或使用包含 /@投影坐标 的完整地图链接')
                if not data.map_center_confirmed:
                    raise HTTPException(422, '此链接包含地图中心坐标，未核实为酒店标记坐标。请确认地图中心对准酒店后勾选确认，或清空链接手动填写准确经纬度')
                lon, lat = baidu_mercator_to_bd09(float(match[1]), float(match[2]))
                system = 'bd09'
        else: raise HTTPException(422, '请使用含坐标的高德或百度地图链接，或清空链接后手动填写坐标')
    if (lat is None) != (lon is None): raise HTTPException(422, '经度和纬度必须同时填写')
    if lat is None: return None
    if not all(math.isfinite(v) for v in (lat,lon)) or not (-90<=lat<=90 and -180<=lon<=180):
        raise HTTPException(422, '地图坐标超出有效范围')
    if system == 'bd09':
        x,y=lon-0.0065,lat-0.006
        z=math.sqrt(x*x+y*y)-0.00002*math.sin(y*math.pi*3000/180)
        theta=math.atan2(y,x)-0.000003*math.cos(x*math.pi*3000/180)
        lon,lat=z*math.cos(theta),z*math.sin(theta)
    if system in ('bd09','gcj02') and 72.004<=lon<=137.8347 and 0.8293<=lat<=55.8271:
        target_lat,target_lon=lat,lon
        for _ in range(5):
            a,b=_gcj_offset(lat,lon)
            lat,lon=target_lat-a,target_lon-b
    return {'latitude':lat,'longitude':lon,'accuracy':100}

def _gcj_offset(lat,lon):
    x,y=lon-105,lat-35
    a=-100+2*x+3*y+0.2*y*y+0.1*x*y+0.2*math.sqrt(abs(x))
    b=300+x+2*y+0.1*x*x+0.1*x*y+0.1*math.sqrt(abs(x))
    wave=(20*math.sin(6*x*math.pi)+20*math.sin(2*x*math.pi))*2/3
    a+=wave+(20*math.sin(y*math.pi)+40*math.sin(y*math.pi/3))*2/3+(160*math.sin(y*math.pi/12)+320*math.sin(y*math.pi/30))*2/3
    b+=wave+(20*math.sin(x*math.pi)+40*math.sin(x*math.pi/3))*2/3+(150*math.sin(x*math.pi/12)+300*math.sin(x*math.pi/30))*2/3
    rad=lat/180*math.pi; magic=1-0.006693421622965943*math.sin(rad)**2
    return a*180/((6378245*(1-0.006693421622965943)/(magic*math.sqrt(magic)))*math.pi), b*180/(6378245/math.sqrt(magic)*math.cos(rad)*math.pi)


# Baidu inverse Mercator bands; reference: gcoord 1.0.6 (MIT), BD09MC.ts.
_BAIDU_MC_BANDS = [12890594.86, 8362377.87, 5591021, 3481989.83, 1678043.12, 0]
_BAIDU_MC_TO_LL = [[1.410526172116255e-08,
  8.98305509648872e-06,
  -1.9939833816331,
  200.9824383106796,
  -187.2403703815547,
  91.6087516669843,
  -23.38765649603339,
  2.57121317296198,
  -0.03801003308653,
  17337981.2],
 [-7.435856389565537e-09,
  8.983055097726239e-06,
  -0.78625201886289,
  96.32687599759846,
  -1.85204757529826,
  -59.36935905485877,
  47.40033549296737,
  -16.50741931063887,
  2.28786674699375,
  10260144.86],
 [-3.030883460898826e-08,
  8.98305509983578e-06,
  0.30071316287616,
  59.74293618442277,
  7.357984074871,
  -25.38371002664745,
  13.45380521110908,
  -3.29883767235584,
  0.32710905363475,
  6856817.37],
 [-1.981981304930552e-08,
  8.983055099779535e-06,
  0.03278182852591,
  40.31678527705744,
  0.65659298677277,
  -4.44255534477492,
  0.85341911805263,
  0.12923347998204,
  -0.04625736007561,
  4482777.06],
 [3.09191371068437e-09,
  8.983055096812155e-06,
  6.995724062e-05,
  23.10934304144901,
  -0.00023663490511,
  -0.6321817810242,
  -0.00663494467273,
  0.03430082397953,
  -0.00466043876332,
  2555164.4],
 [2.890871144776878e-09,
  8.983055095805407e-06,
  -3.068298e-08,
  7.47137025468032,
  -3.53937994e-06,
  -0.02145144861037,
  -1.234426596e-05,
  0.00010322952773,
  -3.23890364e-06,
  826088.5]]

def baidu_mercator_to_bd09(x, y):
    if not (math.isfinite(x) and math.isfinite(y)) or abs(x)>20040000 or abs(y)>13000000:
        raise HTTPException(422, '百度地图投影坐标超出有效范围')
    factors = next(c for band,c in zip(_BAIDU_MC_BANDS,_BAIDU_MC_TO_LL) if abs(y)>=band)
    longitude = factors[0] + factors[1] * abs(x)
    t = abs(y) / factors[9]
    latitude = sum(factors[i+2] * t**i for i in range(7))
    return math.copysign(longitude,x), math.copysign(latitude,y)
