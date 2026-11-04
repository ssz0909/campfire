import io
import shutil
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image, ImageChops, ImageStat

from app.services import video_branding as branding
from app.services.media_processing import inspect_video
from tests.conftest import create_test_user, create_test_company, auth_headers


def test_branding_settings_permissions_validation_and_tenant_isolation(client, db, monkeypatch):
    owner = create_test_user(db)
    company = create_test_company(db, owner)
    other = create_test_company(db, owner, slug='other-brand')
    outsider = create_test_user(db, email='outsider@example.com')
    company.business_goals = {'publish_location_name': '酒店地点', 'default_video_music': {'selection_mode': 'random'}}
    db.commit()
    monkeypatch.setattr(branding, 'brand_font_path', lambda *args: 'test-font')
    url = f'/api/v1/companies/{company.id}/video-branding'
    payload = {'enabled': True, 'text': '安吉雲中溪', 'duration_seconds': 3}
    assert client.put(url, json=payload, headers=auth_headers(outsider)).status_code == 403
    assert client.put(url, json={**payload, 'text': ' '}, headers=auth_headers(owner)).status_code == 422
    for invalid in ({'duration_seconds': 10}, {'text': '酒店\n文字'}, {'text': '酒' * 33}, {'font': '../../etc/passwd'}, {'font_size_percent': 16}, {'position': 'elsewhere'}, {'margin_x_percent': -1}, {'margin_y_percent': 31}):
        assert client.put(url, json={**payload, **invalid}, headers=auth_headers(owner)).status_code == 422
    response = client.put(url, json=payload, headers=auth_headers(owner))
    assert response.status_code == 200, response.text
    assert response.json()['business_goals']['video_branding'] == branding.VideoBrandingSettings(**payload).model_dump()
    assert company.business_goals['publish_location_name'] == '酒店地点'
    assert company.business_goals['default_video_music']['selection_mode'] == 'random'
    render = Mock(return_value=b'branded')
    monkeypatch.setattr(branding, 'add_opening_wordmark', render)
    assert branding.apply_opening_branding(db, SimpleNamespace(company_id=other.id), b'video') == (b'video', None)
    result, metadata = branding.apply_opening_branding(db, SimpleNamespace(company_id=company.id), b'video')
    assert result == b'branded' and metadata['text'] == '安吉雲中溪'
    assert render.call_args.args == (b'video', '安吉雲中溪', 3)
    assert render.call_args.kwargs['style'].position == 'top_center'
    assert client.put(url, json={**payload, 'enabled': False}, headers=auth_headers(owner)).status_code == 200
    assert branding.apply_opening_branding(db, SimpleNamespace(company_id=company.id), b'video') == (b'video', None)


def test_finalization_applies_branding_after_music_only_once(monkeypatch):
    from app.services.video_generation import _finalize_content
    music = Mock(return_value=b'with-music')
    brand = Mock(return_value=(b'branded', {'text': '酒店'}))
    monkeypatch.setattr('app.services.video_music.apply_music', music)
    monkeypatch.setattr(branding, 'apply_opening_branding', brand)
    db, project, storage = object(), object(), object()
    assert _finalize_content(db, project, b'assembled', storage) == (b'branded', {'text': '酒店'})
    music.assert_called_once_with(db, project, b'assembled', storage)
    brand.assert_called_once_with(db, project, b'with-music')


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'), reason='FFmpeg required')
@pytest.mark.parametrize('size,audio', [('720x1280', True), ('1280x720', False), ('960x960', True), ('640x360', True)])
def test_wordmark_is_visible_only_at_opening_and_preserves_media(tmp_path, size, audio):
    source, result = tmp_path / 'input.mp4', tmp_path / 'output.mp4'
    args = ['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'color=c=0x416a6b:s={size}:r=24']
    if audio:
        args += ['-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000', '-c:a', 'aac']
    subprocess.run(args + ['-t', '2', '-c:v', 'libx264', str(source)], check=True, capture_output=True, timeout=30)
    style = branding.VideoBrandingSettings(font='serif', position='bottom_right', margin_x_percent=3, margin_y_percent=5) if size == '640x360' else None
    result.write_bytes(branding.add_opening_wordmark(source.read_bytes(), '安吉雲中溪', 1, style=style))
    props, thumbnail = inspect_video(result.read_bytes())
    assert props['resolution'] == size
    assert props['duration_seconds'] == pytest.approx(2, abs=0.06)
    assert thumbnail.startswith(b'\xff\xd8')
    def frame(path, seconds):
        raw = subprocess.check_output(['ffmpeg', '-v', 'error', '-ss', str(seconds), '-i', str(path),
            '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'png', '-'], timeout=30)
        return Image.open(io.BytesIO(raw)).convert('RGB')
    first, late = frame(result, 0), frame(result, 1.5)
    original = frame(source, 0)
    width, height = first.size
    crop = (round(width * 0.25), round(height * 0.14), round(width * 0.75), round(height * 0.25))
    if style:
        crop = (round(width*.3), round(height*.7), width, height)
    assert max(ImageStat.Stat(ImageChops.difference(first.crop(crop), original.crop(crop))).mean) > 10
    assert max(ImageStat.Stat(ImageChops.difference(late, original)).mean) < 3
    assert sum(1 for pixel in first.crop(crop).getdata() if min(pixel) > 235) > 200
    probe = subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'a',
        '-show_entries', 'stream=codec_type', '-of', 'csv=p=0', str(result)], timeout=30)
    assert (b'audio' in probe) == audio
    if audio:
        def audio_hash(path):
            return subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(path),
                '-map', '0:a:0', '-c:a', 'copy', '-f', 'hash', '-'], timeout=30)
        assert audio_hash(source) == audio_hash(result)
    first.save(tmp_path / 'opening-frame.png')


def test_wordmark_long_name_fits_safe_area():
    image = branding.wordmark_image('安吉雲中溪·汤泉度假酒店' * 2, 720, 1280)
    box = image.getbbox()
    assert box and box[0] >= 720 * 0.08 and box[2] <= 720 * 0.92


@pytest.mark.parametrize('size', [(720,1280),(1280,720),(960,960)])
@pytest.mark.parametrize('position', ['top_left','top_center','top_right','middle_left','middle_center','middle_right','bottom_left','bottom_center','bottom_right'])
def test_custom_layout_bounds_and_anchors(size, position):
    width,height=size
    style=branding.VideoBrandingSettings(font='serif', font_size_percent=15, position=position,
        margin_x_percent=20, margin_y_percent=25)
    box=branding.wordmark_image('安吉雲中溪·汤泉度假酒店',width,height,style).getbbox()
    assert box and box[0]>=width*.20-1 and box[2]<=width*.80+1
    assert box[1]>=height*.25-1 and box[3]<=height*.75+1
    vertical,horizontal=position.split('_')
    if horizontal=='left': assert abs(box[0]-width*.20)<=1
    if horizontal=='right': assert abs(box[2]-width*.80)<=2
    if horizontal=='center': assert abs((box[0]+box[2])/2-width/2)<=1
    if vertical=='top': assert abs(box[1]-height*.25)<=1
    if vertical=='bottom': assert abs(box[3]-height*.75)<=2
    if vertical=='middle': assert abs((box[1]+box[3])/2-height/2)<=1


def test_font_and_size_change_rendered_image():
    small=branding.wordmark_image('安吉雲中溪',720,1280,branding.VideoBrandingSettings(font_size_percent=3))
    large=branding.wordmark_image('安吉雲中溪',720,1280,branding.VideoBrandingSettings(font_size_percent=10))
    assert large.getbbox()[2]-large.getbbox()[0] > small.getbbox()[2]-small.getbbox()[0]
    serif=branding.wordmark_image('安吉雲中溪',720,1280,branding.VideoBrandingSettings(font='serif'))
    assert serif.tobytes()!=branding.wordmark_image('安吉雲中溪',720,1280).tobytes()


def test_preview_is_scoped_validated_and_does_not_save(client, db):
    import base64
    owner=create_test_user(db)
    company=create_test_company(db,owner)
    outsider=create_test_user(db,email='preview-outsider@example.com')
    company.business_goals={'video_branding':{'enabled':True,'text':'原品牌','duration_seconds':1}}
    db.commit()
    url=f'/api/v1/companies/{company.id}/video-branding'
    payload={'enabled':True,'text':'安吉雲中溪','font':'serif','position':'bottom_right','margin_y_percent':5}
    assert client.post(url+'/preview',json=payload,headers=auth_headers(outsider)).status_code==403
    assert client.get(url+'/fonts',headers=auth_headers(outsider)).status_code==403
    fonts=client.get(url+'/fonts',headers=auth_headers(owner)).json()
    assert {'default','sans','serif'}<={item['value'] for item in fonts}
    for aspect in ['9:16','16:9','1:1']:
        response=client.post(url+'/preview',params={'aspect':aspect},json=payload,headers=auth_headers(owner))
        assert response.status_code==200,response.text
        img=Image.open(io.BytesIO(base64.b64decode(response.json()['image_base64'])))
        assert img.getbbox() and max(img.size)<=480
    assert client.post(url+'/preview?aspect=bad',json=payload,headers=auth_headers(owner)).status_code==422
    assert company.business_goals['video_branding']['text']=='原品牌'
    response=client.put(url,json=payload,headers=auth_headers(owner))
    assert response.status_code==200,response.text
    saved=response.json()['business_goals']['video_branding']
    assert saved['font']=='serif' and saved['position']=='bottom_right' and saved['margin_y_percent']==5


def test_unavailable_font_rejected_before_save(client,db,monkeypatch):
    owner=create_test_user(db)
    company=create_test_company(db,owner)
    def unavailable(*args): raise ValueError('所选中文字体未安装')
    monkeypatch.setattr(branding,'brand_font_path',unavailable)
    response=client.put(f'/api/v1/companies/{company.id}/video-branding',
        json={'enabled':True,'text':'酒店','font':'serif'},headers=auth_headers(owner))
    assert response.status_code==422


def test_traditional_hotel_character_is_visible_in_all_fonts():
    for font in ['default','sans','serif']:
        img=branding.wordmark_image('雲',720,1280,branding.VideoBrandingSettings(font=font))
        assert sum(1 for r,g,b,a in img.getdata() if min(r,g,b)>235 and a==255)>100
