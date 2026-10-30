"""Platform LLM settings, read per operation so workers see committed changes."""
import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.connectors.hotel.models import PlatformKeyValue
from app.core.secrets import encrypt_json, _fernet
from app.database import SessionLocal

LLM_SETTINGS_KEY = 'platform.llm.settings'


def get_llm_settings(db: Session | None = None) -> dict[str, str]:
    if db is None:
        with SessionLocal() as session:
            return get_llm_settings(session)
    row = db.get(PlatformKeyValue, LLM_SETTINGS_KEY)
    if row is not None:
        # Fail closed: corrupted credentials must not silently select another account.
        return json.loads(_fernet().decrypt(row.encrypted_value.encode()).decode())
    return {'base_url': settings.LLM_BASE_URL, 'model': settings.LLM_MODEL,
            'api_key': settings.LLM_API_KEY}


def save_llm_settings(db: Session, values: dict[str, str]) -> None:
    row = db.get(PlatformKeyValue, LLM_SETTINGS_KEY)
    if row is None:
        row = PlatformKeyValue(key=LLM_SETTINGS_KEY)
        db.add(row)
    row.encrypted_value = encrypt_json(values)
    row.updated_at = datetime.now(timezone.utc)


VIDEO_SETTINGS_KEY = 'platform.video.settings'


def get_video_settings(db: Session | None = None) -> dict[str, str]:
    if db is None:
        with SessionLocal() as session:
            return get_video_settings(session)
    row = db.get(PlatformKeyValue, VIDEO_SETTINGS_KEY)
    if row is not None:
        return json.loads(_fernet().decrypt(row.encrypted_value.encode()).decode())
    return {'base_url': settings.VIDEO_BASE_URL, 'model': settings.VIDEO_MODEL,
            'api_key': settings.VIDEO_API_KEY}


def save_video_settings(db: Session, values: dict[str, str]) -> None:
    row = db.get(PlatformKeyValue, VIDEO_SETTINGS_KEY)
    if row is None:
        row = PlatformKeyValue(key=VIDEO_SETTINGS_KEY)
        db.add(row)
    row.encrypted_value = encrypt_json(values)
    row.updated_at = datetime.now(timezone.utc)
