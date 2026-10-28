"""Read actual media properties and generate a thumbnail using local FFmpeg tools."""
import json
import subprocess
import tempfile
from pathlib import Path
from fractions import Fraction

def video_dimensions(aspect_ratio):
    dimensions = {'9:16':(720,1280), '16:9':(1280,720), '1:1':(960,960)}
    if aspect_ratio not in dimensions:
        raise ValueError('画面比例仅支持 9:16、16:9、1:1')
    return dimensions[aspect_ratio]

def normalize_reference_image(content, aspect_ratio, framing=None, focal_x=0.5, focal_y=0.5):
    """Preserve the entire subject, with a blurred backdrop for mismatched frames."""
    import io
    from PIL import Image, ImageOps, ImageFilter
    size = video_dimensions(aspect_ratio)
    with Image.open(io.BytesIO(content)) as raw:
        image = ImageOps.exif_transpose(raw).convert('RGB')
        if framing:
            # Director-led cover crop: never teach the model blurred letterbox bands.
            zoom = {'wide':1.0, 'medium':1.12, 'detail':1.3}[framing]
            width, height = image.size
            crop_width, crop_height = width/zoom, height/zoom
            left = min(max(width*focal_x-crop_width/2, 0), width-crop_width)
            top = min(max(height*focal_y-crop_height/2, 0), height-crop_height)
            image = image.crop((round(left),round(top),round(left+crop_width),round(top+crop_height)))
            image = ImageOps.fit(image, size, centering=(focal_x,focal_y))
            buffer = io.BytesIO(); image.save(buffer, 'JPEG', quality=95)
            return buffer.getvalue()
        background = ImageOps.fit(image, size).filter(ImageFilter.GaussianBlur(32))
        foreground = ImageOps.contain(image, size)
        background.paste(foreground, ((size[0]-foreground.width)//2, (size[1]-foreground.height)//2))
        buffer = io.BytesIO()
        background.save(buffer, 'JPEG', quality=92)
        return buffer.getvalue()

def assemble_model_clips(clips, aspect_ratio, duration):
    """Normalize model output dimensions and audio before concatenation."""
    width, height = video_dimensions(aspect_ratio)
    durations = list(duration) if isinstance(duration, (list, tuple)) else [duration]*len(clips)
    if len(durations) != len(clips) or any(value <= 0 for value in durations):
        raise ValueError('镜头剪辑时长与片段数量不匹配')
    with tempfile.TemporaryDirectory(prefix='aiops-model-clips-') as directory:
        root = Path(directory)
        normalized = []
        for index, content in enumerate(clips):
            source = root / f'source-{index}.mp4'
            source.write_bytes(content)
            probe = subprocess.run(['ffprobe','-v','error','-show_entries','stream=codec_type',
                '-of','json',str(source)], capture_output=True, check=True, timeout=30)
            has_audio = any(s.get('codec_type')=='audio' for s in json.loads(probe.stdout).get('streams', []))
            output = root / f'clip-{index}.mp4'
            args = ['ffmpeg','-v','error','-y','-i',str(source)]
            if not has_audio:
                args += ['-f','lavfi','-i','anullsrc=r=48000:cl=stereo']
            filters = (f'[0:v]split=2[bg][fg];[bg]scale={width}:{height}:force_original_aspect_ratio=increase,'
                f'crop={width}:{height},boxblur=20:2[back];'
                f'[fg]scale={width}:{height}:force_original_aspect_ratio=decrease[front];'
                '[back][front]overlay=(W-w)/2:(H-h)/2,setsar=1,fps=24,format=yuv420p[outv]')
            args += ['-filter_complex',filters,'-map','[outv]','-map','0:a:0' if has_audio else '1:a:0',
                '-c:v','libx264','-preset','veryfast','-c:a','aac','-ar','48000','-ac','2',
                '-af','apad','-t',str(durations[index]),'-movflags','+faststart',str(output)]
            subprocess.run(args, capture_output=True, check=True, timeout=240)
            normalized.append(output)
        manifest = root / 'clips.txt'
        manifest.write_text(''.join(f"file '{p.name}'\n" for p in normalized))
        result = root / 'final.mp4'
        subprocess.run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(manifest),
            '-c','copy','-movflags','+faststart',str(result)], capture_output=True, check=True, timeout=240)
        content = result.read_bytes()
        inspect_video(content)
        return content

def inspect_video(content):
    with tempfile.TemporaryDirectory(prefix='aiops-video-') as directory:
        source = Path(directory) / 'input.mp4'
        source.write_bytes(content)
        result = subprocess.run(['ffprobe','-v','error','-protocol_whitelist','file,pipe',
            '-show_entries','stream=codec_type,codec_name,width,height,r_frame_rate:format=duration',
            '-of','json',str(source)],capture_output=True,check=True,timeout=30)
        metadata = json.loads(result.stdout)
        stream = next((s for s in metadata.get('streams',[]) if s.get('codec_type')=='video'),None)
        if not stream:
            raise ValueError('生成结果不包含可播放的视频流')
        duration = float(metadata.get('format',{}).get('duration',0))
        if duration <= 0:
            raise ValueError('视频时长无效')
        thumbnail = Path(directory) / 'thumbnail.jpg'
        subprocess.run(['ffmpeg','-v','error','-protocol_whitelist','file,pipe','-i',str(source),
            '-frames:v','1','-vf','scale=320:-2','-y',str(thumbnail)],
            capture_output=True,check=True,timeout=30)
        try:
            fps = float(Fraction(stream.get('r_frame_rate','0')))
        except (ValueError,ZeroDivisionError):
            fps = None
        return {'width':stream['width'],'height':stream['height'],'duration_seconds':duration,
                'resolution':f"{stream['width']}x{stream['height']}",'codec':stream.get('codec_name'),
                'fps':fps}, thumbnail.read_bytes()

def enrich_video_asset(asset, storage, content=None):
    properties, thumbnail = inspect_video(content if content is not None else storage.get_file(asset.file_key))
    for key,value in properties.items():
        setattr(asset,key,value)
    thumbnail_key = asset.file_key.rsplit('.',1)[0] + '_thumb.jpg'
    asset.thumbnail_url = storage.upload_file(thumbnail,thumbnail_key,'image/jpeg')
    asset.asset_metadata = {**(asset.asset_metadata or {}),'media_verified':True}
