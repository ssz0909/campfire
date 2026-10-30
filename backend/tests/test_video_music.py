import math
import shutil
import struct
import subprocess
import uuid
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from app.models.asset import Asset
from app.schemas.video_project import MusicSettings,VideoProjectCreate,VideoProjectUpdate
from app.services.video_service import VideoService
from app.services.video_music import music_asset
from tests.conftest import create_test_user,create_test_company


def audio_asset(db,company,user):
    a=Asset(company_id=company.id,uploaded_by=user.id,name='配乐',original_filename='music.wav',
        file_key=f'{uuid.uuid4()}.wav',asset_type='audio',mime_type='audio/wav',file_size_bytes=100,
        processing_status='ready',is_available=True)
    db.add(a);db.flush();return a


def test_music_is_tenant_scoped_and_requires_ready_audio(db):
    user=create_test_user(db);company=create_test_company(db,user)
    other=create_test_company(db,user,slug='other-music')
    music=audio_asset(db,company,user)
    assert music_asset(db,company.id,music.id)==music
    with pytest.raises(HTTPException):music_asset(db,other.id,music.id)
    music.processing_status='pending';db.flush()
    with pytest.raises(HTTPException):music_asset(db,company.id,music.id)
    with pytest.raises(ValueError):MusicSettings(music_volume=float('nan'))
    with pytest.raises(ValueError):MusicSettings(music_volume=1.5)


def test_draft_music_saved_and_replacement_preserves_original(db,monkeypatch):
    user=create_test_user(db);company=create_test_company(db,user);music=audio_asset(db,company,user)
    svc=VideoService(db)
    p=svc.create_project(company.id,user.id,VideoProjectCreate(title='酒店',creation_mode='ai_creative',music_asset_id=music.id))
    assert p.music_asset_id==music.id
    svc.update_project(company.id,p.id,VideoProjectUpdate(music_volume=0.4))
    source=Asset(company_id=company.id,uploaded_by=user.id,name='原成片',original_filename='original.mp4',
        file_key='original.mp4',asset_type='video',mime_type='video/mp4',file_size_bytes=10,processing_status='ready')
    db.add(source);db.flush()
    p.output_asset_id=source.id;p.project_status='pending_review';db.commit()
    with pytest.raises(HTTPException):svc.update_project(company.id,p.id,VideoProjectUpdate(music_asset_id=music.id))
    storage=Mock();storage.get_file.return_value=b'original';storage.upload_file.return_value='/files/new.mp4'
    monkeypatch.setattr('app.services.storage_service.StorageService',lambda *args:storage)
    apply=Mock(return_value=b'remixed')
    monkeypatch.setattr('app.services.video_music.apply_music',apply)
    monkeypatch.setattr('app.services.media_processing.enrich_video_asset',lambda *args:None)
    p=svc.replace_music(company.id,p.id,user.id,MusicSettings(music_asset_id=music.id,music_volume=0.3))
    assert p.output_asset_id!=source.id and p.project_status=='pending_review'
    assert db.get(Asset,source.id).file_key=='original.mp4'
    assert apply.call_args.args[2]==b'original'
    p.project_status='completed';db.commit()
    with pytest.raises(HTTPException):svc.replace_music(company.id,p.id,user.id,MusicSettings(music_asset_id=music.id))


def test_music_failure_rolls_back_without_changing_committed_video(tmp_path,monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.models.base import Base
    engine=create_engine('sqlite:///'+str(tmp_path/'rollback.sqlite'))
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user=create_test_user(db);company=create_test_company(db,user);music=audio_asset(db,company,user)
        p=VideoService(db).create_project(company.id,user.id,VideoProjectCreate(title='原成片',creation_mode='ai_creative'))
        source=Asset(company_id=company.id,uploaded_by=user.id,name='原片',original_filename='video.mp4',file_key='original.mp4',
            asset_type='video',mime_type='video/mp4',file_size_bytes=10,processing_status='ready')
        db.add(source);db.flush();p.output_asset_id=source.id;p.project_status='pending_review';db.commit()
        source_id=source.id
        monkeypatch.setattr('app.services.storage_service.StorageService',lambda *args:Mock())
        monkeypatch.setattr('app.services.video_music.apply_music',Mock(side_effect=ValueError('invalid music')))
        with pytest.raises(HTTPException):VideoService(db).replace_music(company.id,p.id,user.id,MusicSettings(music_asset_id=music.id))
        db.refresh(p)
        assert p.output_asset_id==source_id and p.music_asset_id is None
    engine.dispose()


@pytest.mark.skipif(not shutil.which('ffprobe'),reason='ffprobe required')
def test_wav_upload_is_processed_and_selectable(client,db,monkeypatch,tmp_path):
    import io,wave
    from app.config import settings
    from tests.conftest import auth_headers
    user=create_test_user(db);company=create_test_company(db,user)
    monkeypatch.setattr(settings,'STORAGE_BACKEND','local')
    monkeypatch.setattr(settings,'LOCAL_STORAGE_PATH',str(tmp_path))
    monkeypatch.setattr(settings,'TASK_EXECUTION_MODE','inline')
    stream=io.BytesIO()
    with wave.open(stream,'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000)
        w.writeframes(b'\x00\x00'*8000)
    response=client.post(f'/api/v1/companies/{company.id}/assets/upload',headers=auth_headers(user),
        files={'file':('hotel-music.wav',stream.getvalue(),'audio/wav')})
    assert response.status_code==201,response.text
    data=response.json()
    assert data['asset_type']=='audio' and data['processing_status']=='ready'
    assert data['duration_seconds']==pytest.approx(1,abs=0.02)
    created=client.post(f'/api/v1/companies/{company.id}/video-projects',headers=auth_headers(user),
        json={'title':'酒店配乐','creation_mode':'ai_creative','music_asset_id':data['id'],'music_volume':0.35})
    assert created.status_code==201,created.text
    assert created.json()['music_asset_id']==data['id']


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'),reason='FFmpeg required')
@pytest.mark.parametrize('leading_silence',[0,2.2])
def test_real_music_replaces_audio_loops_and_keeps_video(tmp_path,leading_silence):
    from app.services.media_processing import replace_background_music,inspect_video,inspect_audio
    video=tmp_path/'original.mp4';music=tmp_path/'music.wav';output=tmp_path/'result.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=blue:s=160x240:r=24',
        '-f','lavfi','-i','sine=frequency=1000:sample_rate=48000','-t','3','-c:v','libx264','-c:a','aac',str(video)],check=True,capture_output=True,timeout=30)
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','sine=frequency=440:sample_rate=48000',
        '-af',f'adelay={int(leading_silence*1000)}:all=1','-t',str(leading_silence+0.6),str(music)],check=True,capture_output=True,timeout=30)
    assert inspect_audio(music.read_bytes())['duration_seconds']==pytest.approx(leading_silence+0.6,abs=0.02)
    content=replace_background_music(video.read_bytes(),music.read_bytes(),0.5);output.write_bytes(content)
    properties,_=inspect_video(content)
    assert properties['duration_seconds']==pytest.approx(3,abs=0.1)
    def frames(path):
        return subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-map','0:v:0','-f','framemd5','-'],timeout=30)
    assert frames(video)==frames(output)
    pcm=subprocess.check_output(['ffmpeg','-v','error','-ss','1.2','-i',str(output),'-t','0.25',
        '-vn','-ar','8000','-ac','1','-f','s16le','-'],timeout=30)
    samples=struct.unpack('<'+'h'*(len(pcm)//2),pcm)
    def energy(frequency):
        return sum(v*math.sin(2*math.pi*frequency*i/8000) for i,v in enumerate(samples))**2+sum(v*math.cos(2*math.pi*frequency*i/8000) for i,v in enumerate(samples))**2
    assert energy(440)>100*energy(1000)
    with pytest.raises((ValueError,subprocess.CalledProcessError)):replace_background_music(video.read_bytes(),b'invalid',0.3)
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t','1',str(music)],check=True,capture_output=True,timeout=30)
    with pytest.raises((ValueError,subprocess.CalledProcessError)):replace_background_music(video.read_bytes(),music.read_bytes(),0.3)


def test_company_defaults_apply_to_agent_projects_and_explicit_opt_out(db):
    from app.services.video_music import set_default_music,resolve_music_settings
    from app.services.task_handoff import create_video_handoff
    from app.models.task import OperationTask
    from tests.test_asset_intelligence import make_asset
    user=create_test_user(db);company=create_test_company(db,user);music=audio_asset(db,company,user)
    company.business_goals={'publish_location_name':'保留酒店定位'};db.commit()
    set_default_music(db,company.id,MusicSettings(music_asset_id=music.id,music_volume=0.4))
    assert company.business_goals['publish_location_name']=='保留酒店定位'
    settings=resolve_music_settings(db,company.id)
    assert settings['music_asset_id']==music.id and settings['music_volume']==0.4
    p=VideoService(db).create_project(company.id,user.id,VideoProjectCreate(title='默认配乐',creation_mode='ai_creative'))
    assert p.music_asset_id==music.id
    silent=VideoService(db).create_project(company.id,user.id,VideoProjectCreate(title='取消默认',creation_mode='ai_creative',music_asset_id=None))
    assert silent.music_asset_id is None
    for i in range(12):make_asset(db,company,user,f'风景{i}','landscape',[],'山景')
    task=OperationTask(company_id=company.id,created_by=user.id,title='酒店宣传',task_type='video_generation',status='completed',output={})
    db.add(task);db.commit()
    agent_project=create_video_handoff(db,task)
    assert agent_project.music_asset_id==music.id and agent_project.music_volume==0.4
    set_default_music(db,company.id,MusicSettings())
    assert resolve_music_settings(db,company.id)['music_asset_id'] is None
    assert agent_project.music_asset_id==music.id  # Changes do not rewrite existing projects.


def test_random_music_uses_only_available_tenant_audio_and_persists_choice(db,monkeypatch):
    from app.services.video_music import set_default_music,resolve_music_settings
    from app.schemas.video_project import DefaultMusicSettings
    user=create_test_user(db);company=create_test_company(db,user)
    other=create_test_company(db,user,slug='random-other')
    first=audio_asset(db,company,user);second=audio_asset(db,company,user)
    audio_asset(db,other,user)
    unavailable=audio_asset(db,company,user);unavailable.is_available=False
    pending=audio_asset(db,company,user);pending.processing_status='pending'
    db.commit()
    set_default_music(db,company.id,DefaultMusicSettings(selection_mode='random',music_volume=0.3))
    picks=iter([first.id,second.id])
    def choose(candidates):
        assert {item[0] for item in candidates}=={first.id,second.id}
        return (next(picks),)
    choose_mock=Mock(side_effect=choose)
    monkeypatch.setattr('app.services.video_music.random.choice',choose_mock)
    svc=VideoService(db)
    a=svc.create_project(company.id,user.id,VideoProjectCreate(title='随机一',creation_mode='ai_creative'))
    b=svc.create_project(company.id,user.id,VideoProjectCreate(title='随机二',creation_mode='ai_creative'))
    assert (a.music_asset_id,b.music_asset_id)==(first.id,second.id)
    assert svc.get_project(company.id,a.id).music_asset_id==first.id
    assert choose_mock.call_count==2
    assert resolve_music_settings(db,company.id,{'music_asset_id':None})['music_asset_id'] is None
    first.is_available=False;second.is_available=False;db.commit()
    with pytest.raises(HTTPException,match='') as exc:resolve_music_settings(db,company.id)
    assert '暂无可用音频' in exc.value.detail
