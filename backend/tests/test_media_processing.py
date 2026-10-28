import shutil
import subprocess
import pytest
from app.services.media_processing import inspect_video

@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'), reason='FFmpeg tools required')
def test_real_video_metadata_and_thumbnail(tmp_path):
    source=tmp_path/'sample.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=160x240:r=10',
        '-t','1','-c:v','mpeg4','-y',str(source)],check=True,capture_output=True,timeout=20)
    metadata,thumbnail=inspect_video(source.read_bytes())
    assert metadata['width']==160 and metadata['height']==240
    assert metadata['duration_seconds']>0
    assert thumbnail.startswith(bytes([255,216]))

def test_invalid_media_is_rejected():
    if not shutil.which('ffprobe'): pytest.skip('ffprobe required')
    with pytest.raises(subprocess.CalledProcessError):
        inspect_video(b'not a video')

@pytest.mark.parametrize('size', [(640,360), (360,640)])
def test_reference_image_normalization_preserves_subject(size):
    import io
    from PIL import Image
    from app.services.media_processing import normalize_reference_image
    source = io.BytesIO()
    Image.new('RGB', size, (220,20,20)).save(source, 'PNG')
    normalized = Image.open(io.BytesIO(normalize_reference_image(source.getvalue(), '9:16')))
    assert normalized.size == (720,1280)
    assert normalized.getpixel((360,640))[0] > 200

@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'), reason='FFmpeg tools required')
@pytest.mark.parametrize('durations,expected', [(0.5,1.0), ([0.25,0.5],0.75)])
def test_mixed_orientation_clips_with_and_without_audio_are_unified(tmp_path,durations,expected):
    from app.services.media_processing import assemble_model_clips
    clips = []
    for number, size in enumerate(('320x180', '180x320')):
        source = tmp_path / f'{number}.mp4'
        args = ['ffmpeg','-v','error','-y','-f','lavfi','-i',f'testsrc2=s={size}:r=24']
        if number == 0:
            args += ['-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-c:a','aac']
        subprocess.run(args + ['-t','0.5','-c:v','libx264',str(source)], check=True, capture_output=True, timeout=30)
        clips.append(source.read_bytes())
    content = assemble_model_clips(clips, '9:16', durations)
    metadata, thumbnail = inspect_video(content)
    assert (metadata['width'], metadata['height']) == (720,1280)
    assert expected-0.1 < metadata['duration_seconds'] < expected+0.3
    assert thumbnail.startswith(bytes([255,216]))
