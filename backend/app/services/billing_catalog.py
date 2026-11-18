"""Versioned commercial settings; edits do not change paid order snapshots."""
import copy
import json
from datetime import datetime, timezone
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session
from app.connectors.hotel.models import PlatformKeyValue
from app.core.secrets import encrypt_json, _fernet

KEY = 'platform.billing.catalog'
# One point is represented by 1,000,000 integer units to avoid token rounding loss.
SCALE = 1_000_000
DEFAULT = {
    'enforce_billing': False,
    'video_cost_fen_per_second': 50, 'llm_input_cost_fen_per_million': 200,
    'llm_output_cost_fen_per_million': 1000,
    'video_points_per_second': 50, 'llm_input_points_per_million': 200,
    'llm_output_points_per_million': 1000,
    'plans': [
        {'code': 'starter', 'name': '轻运营版', 'price_fen': 19900, 'included_points': 6000, 'enabled': True},
        {'code': 'growth', 'name': '增长版', 'price_fen': 59900, 'included_points': 20000, 'enabled': True},
        {'code': 'matrix', 'name': '矩阵版', 'price_fen': 149900, 'included_points': 60000, 'enabled': True},
    ],
}


class Plan(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    code: str = Field(pattern=r'^[a-z][a-z0-9_]{1,29}$')
    name: str = Field(min_length=1, max_length=60)
    price_fen: int = Field(gt=0, le=10_000_000, strict=True)
    included_points: int = Field(gt=0, le=100_000_000, strict=True)
    enabled: bool = True


class Catalog(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enforce_billing: bool = False
    video_cost_fen_per_second: int = Field(gt=0, le=100000, strict=True)
    llm_input_cost_fen_per_million: int = Field(gt=0, le=10000000, strict=True)
    llm_output_cost_fen_per_million: int = Field(gt=0, le=10000000, strict=True)
    video_points_per_second: int = Field(gt=0, le=100000, strict=True)
    llm_input_points_per_million: int = Field(gt=0, le=10000000, strict=True)
    llm_output_points_per_million: int = Field(gt=0, le=10000000, strict=True)
    plans: list[Plan] = Field(min_length=1, max_length=12)


def get_catalog(db: Session) -> dict:
    row = db.get(PlatformKeyValue, KEY)
    if row is None:
        return copy.deepcopy(DEFAULT)
    return Catalog.model_validate(json.loads(_fernet().decrypt(row.encrypted_value.encode()))).model_dump()


def save_catalog(db: Session, values: Catalog):
    from fastapi import HTTPException
    data = values.model_dump()
    codes = [p['code'] for p in data['plans']]
    if len(set(codes)) != len(codes):
        raise HTTPException(422, '套餐标识不能重复')
    row = db.get(PlatformKeyValue, KEY)
    if row is None:
        row = PlatformKeyValue(key=KEY); db.add(row)
    row.encrypted_value = encrypt_json(data)
    row.updated_at = datetime.now(timezone.utc)
    return data
