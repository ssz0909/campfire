"""
Tests for the 订单来了 connector.

The crypto tests deliberately use the *sample* values printed in the vendor's
API document (a demo keypair/message) — they are not real credentials — so the
implementation is checked against the platform's own reference data.
"""
from __future__ import annotations

import base64
import json

import httpx
import pytest

from app.connectors.hotel.crypto import (
    aes_decrypt,
    load_private_key_der,
    sign,
    signature_content,
    verify,
)
from app.config import settings

# ---- Vendor sample values (demo data from 订单来了API.docx) ------------------
SAMPLE_AES_KEY = "HqXwpOy5vJPr1IgOg3JU1RuGhxCaofWzU5zr8VlWRvs="
SAMPLE_PLATFORM_PUBLIC_KEY = (
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAkncEuv0hUcgwmtQAd32P4Ea/KMXo+B4WXtiejKXQxA7afV3JqEa50jcQalwDGCo0KJDCwcJEcsasaLxDg6YBWgtQKl86HDcsSDT3JJSGnMp48sSqN6xuMyMRKsgBjxwBtbZ+dYDOSuELznTqyL8iNIpIvD3uWiqXQ9qgLznpDg4vZnBwXu0xUaevj5WD0gY1nKNdvCsbaLDRlOpTWyb04bGt5NmqncB9rWRzOJn31wUcSH/5OX2q65qvSVb/yLhR2ZBzsfKCq8b6o6+oymsrQort6P5Ymt95qPT/ucX2ITJlxp+35HyXYUj4dvFIkPZ18/bh5pZ+4Zf8iTdQHqcJzwIDAQAB"
)
SAMPLE_MSG = (
    "43jjzMtzwOKLeCyJ6vwFGRoD0AfmmFEJmo7t+JZZcoS4KF4RZKjZJXAm5cE14y4PjVy/tBzwwKDQp/XQg2tVd/N489hUeR/RMEGh6mHwA8Kd0LP+3tEeIqZ15v57csuHle4y5D4p65mnpQ0NMnw7AddA+uYAz39adBhHTfxLoxhhE9zTmrtlJZKXb24SezGzGt88R9fN+ZBHy2+KDlOBAZ1yrXGZQ+DkG/uTmptd4Etw1Jkf+WiMEQDhHYUEtenG"
)
SAMPLE_SIGN = (
    "VRlIYhXXjOAwJW5SeiCycUepMHwp9H8N5oX2T9NM+Z3PxF6uPmMgG3Lq+Xkv7lV7ncop9Bo3+TlKdTbT1v1c3O+TNi1JK7F3JdWN8sOX4uvbcPVtnrFnodWdQi3KMeYUnyt/QRZpeEo5p3qzpCxHC9zgWONyhvlGeybRTJ0i+SDS/Jy2vcUHgcqJNZ5sjcaUn3GFZwNVZ5AAR68rEvCl/w/J7vstopCrq7ORWFBnRjy2kDsBWiMGnNgQ3ODWCi7uX3bXQ781b3bLs6mf7hJqUrhEW2Ko0HKURG9kME8ujCx7r63mLFIdvVD7Gt1H08/dar4nVpEWR4FxX5wnsULABQ=="
)
SAMPLE_BODY = {
    "appCode": 1412761285093765120,
    "timestamp": 1756891202946,
    "nonce": 113,
}


# ---------------------------------------------------------------------------
# Crypto
# ---------------------------------------------------------------------------

def test_decrypt_matches_vendor_sample():
    message = aes_decrypt(SAMPLE_MSG, SAMPLE_AES_KEY)
    parsed = json.loads(message)
    assert parsed["action"] == "TICKET"
    assert "ticket" in parsed["reqMsg"]


def test_callback_signature_verifies_with_vendor_sample():
    message = aes_decrypt(SAMPLE_MSG, SAMPLE_AES_KEY)
    content = signature_content(
        {
            "appCode": str(SAMPLE_BODY["appCode"]),
            "timestamp": str(SAMPLE_BODY["timestamp"]),
            "nonce": str(SAMPLE_BODY["nonce"]),
            "msg": message,
        }
    )
    assert verify(content, SAMPLE_SIGN, SAMPLE_PLATFORM_PUBLIC_KEY) is True


def test_tampered_message_fails_verification():
    message = aes_decrypt(SAMPLE_MSG, SAMPLE_AES_KEY).replace("TICKET", "TICKEX")
    content = signature_content(
        {
            "appCode": str(SAMPLE_BODY["appCode"]),
            "timestamp": str(SAMPLE_BODY["timestamp"]),
            "nonce": str(SAMPLE_BODY["nonce"]),
            "msg": message,
        }
    )
    assert verify(content, SAMPLE_SIGN, SAMPLE_PLATFORM_PUBLIC_KEY) is False


def test_signature_content_is_sorted():
    content = signature_content({"version": "3.0", "appCode": "1", "timestamp": "2"})
    assert content == "appCode=1&timestamp=2&version=3.0"


def test_local_keypair_signs_and_verifies():
    """The operator's key files exist and are a valid PKCS#8/X.509 pair."""
    from pathlib import Path

    if not Path(settings.DDLL_PRIVATE_KEY_PATH).exists() and not settings.DDLL_PRIVATE_KEY:
        pytest.skip("no local private key configured")
    der = load_private_key_der(settings.DDLL_PRIVATE_KEY_PATH)
    signature = sign("hello", der)
    public_der = der  # signing/verifying uses the same key material for a round trip
    from cryptography.hazmat.primitives import serialization

    public_b64 = base64.b64encode(
        serialization.load_der_private_key(der, None)
        .public_key()
        .public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    ).decode()
    assert verify("hello", signature, public_b64) is True


# ---------------------------------------------------------------------------
# Client: signing + endpoint mapping (mocked transport)
# ---------------------------------------------------------------------------

def _record_transport(monkeypatch, responses: dict[str, dict]):
    """Return an httpx mock transport that records requests per path."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        for path, payload in responses.items():
            if request.url.path.endswith(path):
                return httpx.Response(200, json=payload)
        return httpx.Response(200, json={"code": "1", "msg": "成功", "data": {}})

    return httpx.MockTransport(handler), calls


def _make_key():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        serialization.Encoding.DER,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


@pytest.mark.asyncio
async def test_client_signs_every_request():
    from app.connectors.hotel.client import DdllClient

    transport, calls = _record_transport(monkeypatch=None, responses={})
    client = DdllClient(
        app_code="123",
        app_secret="secret",
        auth_access_token="store-token",
        private_key_der=_make_key(),
        base_url="https://open.dingdanll.com",
        transport=transport,
    )
    await client.fetch_hotel(77778889)
    assert calls, "expected an HTTP call"
    req = calls[0]
    assert req.headers["appcode"] == "123"
    assert req.headers["version"] == settings.DDLL_API_VERSION
    assert req.headers["sign"]
    assert req.url.params["authAccessToken"] == "store-token"


@pytest.mark.asyncio
async def test_order_search_and_detail_parse_data():
    from app.connectors.hotel.client import DdllClient

    transport, calls = _record_transport(
        monkeypatch=None,
        responses={
            "/order/search": {"code": "1", "data": {"list": ["A1"], "boolLastPage": True}},
            "/order/detail": {"code": "1", "data": {"list": [{"orderNum": "A1", "status": 3}]}},
        },
    )
    client = DdllClient(
        app_code="123", app_secret="s", auth_access_token="t",
        private_key_der=_make_key(), transport=transport,
    )
    search = await client.search_orders(
        hotel_num=1, date_type=1, begin_date="2026-01-01", end_date="2026-01-31"
    )
    assert search["list"] == ["A1"]
    detail = await client.order_detail(hotel_num=1, order_num="A1")
    assert detail["list"][0]["status"] == 3


@pytest.mark.asyncio
async def test_error_code_raises_with_message():
    from app.connectors.hotel.client import DdllApiError, DdllClient

    transport, _ = _record_transport(
        monkeypatch=None,
        responses={"/order/detail": {"code": "AO-50017", "msg": ""}},
    )
    client = DdllClient(
        app_code="1", app_secret="s", auth_access_token="t",
        private_key_der=_make_key(), transport=transport,
    )
    with pytest.raises(DdllApiError) as exc:
        await client.order_detail(hotel_num=1, order_num="X")
    assert exc.value.code == "AO-50017"
    assert "未找到订单" in exc.value.message


@pytest.mark.asyncio
async def test_store_token_required():
    from app.connectors.hotel.client import DdllApiError, DdllClient

    client = DdllClient(
        app_code="1", app_secret="s", auth_access_token=None,
        private_key_der=_make_key(), transport=httpx.MockTransport(lambda r: httpx.Response(200)),
    )
    with pytest.raises(DdllApiError) as exc:
        await client.fetch_hotel(1)
    assert exc.value.code == "NO_STORE_TOKEN"


# ---------------------------------------------------------------------------
# Service / API (SQLite in-memory DB, mocked platform)
# ---------------------------------------------------------------------------

from datetime import datetime  # noqa: E402

from tests.conftest import auth_headers, create_test_company, create_test_user  # noqa: E402


def _detail(order_num="A1", status=3, amount=588.0, phone="13800001234", id_no="330102199001011234"):
    return {
        "list": [
            {
                "orderNum": order_num,
                "status": status,
                "channelType": 1,
                "channelName": "携程",
                "payType": 1,
                "currency": "CNY",
                "actualAmount": amount,
                "paidAmount": amount,
                "createTime": "2026-10-01 10:00:00",
                "reserveName": "张三",
                "reservePhone": phone,
                "accomOrderInfos": [
                    {
                        "roomCode": 11,
                        "roomTypeName": "大床房",
                        "status": 40,
                        "checkInTime": "2026-10-05 14:00:00",
                        "checkOutTime": "2026-10-07 12:00:00",
                        "residentInfos": [
                            {"name": "李四", "phone": phone, "identityNo": id_no}
                        ],
                        "dateAmountInfos": [
                            {"date": "2026-10-05", "amount": 294.0},
                            {"date": "2026-10-06", "amount": 294.0},
                        ],
                    },
                    {  # cancelled room: must not count towards nights
                        "roomCode": 12,
                        "status": 50,
                        "checkInTime": "2026-10-05 14:00:00",
                        "checkOutTime": "2026-10-06 12:00:00",
                        "dateAmountInfos": [{"date": "2026-10-05", "amount": 100.0}],
                    },
                ],
            }
        ]
    }


def test_upsert_redacts_personal_data_and_derives_nights(db):
    from app.connectors.hotel.service import HotelConnectorService

    owner = create_test_user(db, email="hotel_owner@example.com")
    company = create_test_company(db, owner, slug="hotel-co")
    svc = HotelConnectorService(company.id, db)
    order = svc._upsert_order(1001, "A1", _detail())
    db.commit()

    assert order.room_nights == 2          # cancelled room excluded
    assert order.room_count == 1
    assert order.check_in_at.day == 5 and order.check_out_at.day == 7
    blob = json.dumps(order.detail, ensure_ascii=False)
    assert "330102199001011234" not in blob   # ID number removed
    assert "张三" not in blob and "李四" not in blob  # names removed
    assert "13800001234" not in blob          # phone masked


def test_upsert_is_idempotent(db):
    from app.connectors.hotel.models import HotelOrder
    from app.connectors.hotel.service import HotelConnectorService

    owner = create_test_user(db, email="hotel_idem@example.com")
    company = create_test_company(db, owner, slug="hotel-idem")
    svc = HotelConnectorService(company.id, db)
    svc._upsert_order(1001, "A1", _detail(status=2))
    db.commit()
    svc._upsert_order(1001, "A1", _detail(status=7, amount=700.0))
    db.commit()
    rows = db.query(HotelOrder).filter(HotelOrder.company_id == company.id).all()
    assert len(rows) == 1
    assert rows[0].status == 7 and float(rows[0].actual_amount) == 700.0


def test_metrics_report_insufficient_data_instead_of_guessing(db):
    from app.connectors.hotel.service import HotelConnectorService

    owner = create_test_user(db, email="hotel_metrics@example.com")
    company = create_test_company(db, owner, slug="hotel-metrics")
    svc = HotelConnectorService(company.id, db)
    svc.save_config(hotel_num=1001, auth_access_token="tok")
    svc._upsert_order(1001, "A1", _detail())
    svc._upsert_order(1001, "A2", _detail(order_num="A2", status=4, amount=300.0))
    db.commit()

    m = svc.metrics("2026-10-01", "2026-10-31")
    assert m["total_orders"] == 2 and m["cancelled_orders"] == 1
    assert m["cancellation_rate"] == 0.5
    assert m["revenue"] == 588.0                      # cancelled order excluded
    assert m["average_room_nightly_rate"] == 294.0
    assert m["occupancy_rate"] is None                # no room count known yet
    assert "数据不足" in m["occupancy_note"]

    cfg = svc.get_config()
    cfg.room_count = 10
    db.commit()
    m2 = svc.metrics("2026-10-01", "2026-10-31")
    assert m2["occupancy_rate"] == round(2 / (10 * 31), 4)


def test_credentials_encrypted_and_never_returned(client, db):
    owner = create_test_user(db, email="hotel_cfg@example.com")
    company = create_test_company(db, owner, slug="hotel-cfg")
    resp = client.post(
        f"/api/v1/companies/{company.id}/connectors/hotel",
        json={"hotel_num": 1001, "auth_access_token": "super-secret-token-123"},
        headers=auth_headers(owner),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "super-secret-token-123" not in json.dumps(body)
    assert body["auth_access_token"].endswith("***")

    from app.connectors.hotel.models import HotelConnectorConfig

    stored = db.query(HotelConnectorConfig).filter_by(company_id=company.id).one()
    assert "super-secret-token-123" not in (stored.encrypted_credentials or "")


def test_tenant_isolation_on_orders_and_config(client, db):
    from app.connectors.hotel.service import HotelConnectorService

    a = create_test_user(db, email="hotel_a@example.com")
    b = create_test_user(db, email="hotel_b@example.com")
    ca = create_test_company(db, a, slug="hotel-a")
    create_test_company(db, b, slug="hotel-b")
    HotelConnectorService(ca.id, db)._upsert_order(1001, "A1", _detail())
    db.commit()

    # B cannot read A's connector data
    assert client.get(
        f"/api/v1/companies/{ca.id}/connectors/hotel/orders", headers=auth_headers(b)
    ).status_code == 403
    assert client.get(
        f"/api/v1/companies/{ca.id}/analytics/orders", headers=auth_headers(b)
    ).status_code == 403
    # A can
    ok = client.get(
        f"/api/v1/companies/{ca.id}/connectors/hotel/orders", headers=auth_headers(a)
    )
    assert ok.status_code == 200 and ok.json()["count"] == 1


def test_same_store_cannot_bind_to_two_companies(client, db):
    a = create_test_user(db, email="bind_a@example.com")
    b = create_test_user(db, email="bind_b@example.com")
    ca = create_test_company(db, a, slug="bind-a")
    cb = create_test_company(db, b, slug="bind-b")
    payload = {"hotel_num": 5555, "auth_access_token": "t"}
    assert client.post(f"/api/v1/companies/{ca.id}/connectors/hotel", json=payload,
                       headers=auth_headers(a)).status_code == 200
    r = client.post(f"/api/v1/companies/{cb.id}/connectors/hotel", json=payload,
                    headers=auth_headers(b))
    assert r.status_code == 409


def test_sync_requires_configuration_and_rejects_old_window(client, db):
    owner = create_test_user(db, email="sync_owner@example.com")
    company = create_test_company(db, owner, slug="sync-co")
    url = f"/api/v1/companies/{company.id}/connectors/hotel/sync"
    assert client.post(url, json={}, headers=auth_headers(owner)).status_code == 409

    client.post(f"/api/v1/companies/{company.id}/connectors/hotel",
                json={"hotel_num": 777, "auth_access_token": "t"}, headers=auth_headers(owner))
    old = client.post(url, json={"begin_date": "2020-01-01"}, headers=auth_headers(owner))
    assert old.status_code == 422  # platform only exposes the last 90 days


@pytest.mark.asyncio
async def test_run_sync_end_to_end_with_mocked_platform(db, monkeypatch):
    from app.connectors.hotel import service as svc_mod
    from app.connectors.hotel.models import HotelOrder

    owner = create_test_user(db, email="e2e_owner@example.com")
    company = create_test_company(db, owner, slug="e2e-co")
    svc = svc_mod.HotelConnectorService(company.id, db)
    svc.save_config(hotel_num=4242, auth_access_token="tok")

    class FakeClient:
        async def search_orders(self, **kw):
            return {"list": ["A1", "A2"], "boolLastPage": True}

        async def order_detail(self, *, hotel_num, order_num):
            if order_num == "A2":
                from app.connectors.hotel.client import DdllApiError
                raise DdllApiError("AO-50017", "未找到订单或无权限", endpoint="detail")
            return _detail(order_num=order_num)

    monkeypatch.setattr(svc, "_client", lambda config: FakeClient())
    job = await svc.create_sync_job()
    job = await svc.run_sync(job)

    assert job.status == "success"
    assert job.orders_found == 2 and job.orders_synced == 1 and job.orders_failed == 0
    rows = {o.order_num: o for o in db.query(HotelOrder).all() if o.company_id == company.id}
    assert set(rows) == {"A1"}  # A2 vanished upstream -> not stored as a fake record


# ---------------------------------------------------------------------------
# Callback endpoint security
# ---------------------------------------------------------------------------

def _encrypt_like_vendor(message: str, key_b64: str) -> str:
    """Inverse of aes_decrypt, used to craft authentic callback bodies in tests."""
    import os
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    key = base64.b64decode(key_b64)
    body = os.urandom(16) + len(message.encode()).to_bytes(4, "big") + message.encode()
    pad = 32 - (len(body) % 32)
    body += bytes([pad]) * pad
    enc = Cipher(algorithms.AES(key), modes.CBC(key[:16])).encryptor()
    return base64.b64encode(enc.update(body) + enc.finalize()).decode()


@pytest.fixture()
def callback_env(monkeypatch):
    """A self-contained platform: our test keypair stands in for the platform's."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    der_priv = key.private_bytes(
        serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    pub_b64 = base64.b64encode(
        key.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    ).decode()
    aes_b64 = base64.b64encode(b"k" * 32).decode()
    monkeypatch.setattr(settings, "DDLL_AES_KEY", aes_b64)
    monkeypatch.setattr(settings, "DDLL_PLATFORM_PUBLIC_KEY", pub_b64)
    monkeypatch.setattr(settings, "DDLL_APP_CODE", "999")
    return der_priv, aes_b64


def _callback_body(callback_env, message: dict, *, app_code="999", timestamp=None, tamper=False):
    import time

    der_priv, aes_b64 = callback_env
    text = json.dumps(message, ensure_ascii=False)
    ts = str(timestamp if timestamp is not None else int(time.time() * 1000))
    content = signature_content(
        {"appCode": app_code, "timestamp": ts, "nonce": "113", "msg": text}
    )
    sig = sign(content, der_priv)
    if tamper:
        sig = sign(content + "x", der_priv)
    return {
        "msg": _encrypt_like_vendor(text, aes_b64),
        "sign": sig,
        "appCode": int(app_code),
        "nonce": 113,
        "timestamp": int(ts),
    }


def test_callback_ticket_is_stored_encrypted(client, db, callback_env):
    msg = {"action": "TICKET", "reqMsg": json.dumps({"ticket": "T-123", "expire": 1})}
    r = client.post("/api/v1/callbacks/ddll", json=_callback_body(callback_env, msg))
    assert r.status_code == 200 and r.json()["code"] == "1"

    from app.connectors.hotel.models import PlatformKeyValue
    from app.connectors.hotel.service import get_ticket

    assert get_ticket(db)["ticket"] == "T-123"
    assert "T-123" not in db.get(PlatformKeyValue, "ddll_ticket").encrypted_value


def test_callback_rejects_bad_signature(client, callback_env):
    msg = {"action": "TICKET", "reqMsg": json.dumps({"ticket": "evil"})}
    r = client.post("/api/v1/callbacks/ddll", json=_callback_body(callback_env, msg, tamper=True))
    assert r.status_code == 403


def test_callback_rejects_unknown_app_and_stale_timestamp(client, callback_env):
    msg = {"action": "TICKET", "reqMsg": json.dumps({"ticket": "x"})}
    assert client.post("/api/v1/callbacks/ddll",
                       json=_callback_body(callback_env, msg, app_code="111")).status_code == 403
    assert client.post("/api/v1/callbacks/ddll",
                       json=_callback_body(callback_env, msg, timestamp=1_000_000_000_000)
                       ).status_code == 400


def test_callback_rejects_garbage(client, callback_env):
    assert client.post("/api/v1/callbacks/ddll", json={"nope": 1}).status_code == 400
    assert client.post("/api/v1/callbacks/ddll", json={
        "msg": "AAAA", "sign": "x", "appCode": 999, "nonce": 1, "timestamp": 1
    }).status_code == 400


def test_callback_order_change_updates_only_owning_tenant(client, db, callback_env):
    from app.connectors.hotel.models import HotelOrder
    from app.connectors.hotel.service import HotelConnectorService

    a = create_test_user(db, email="cb_a@example.com")
    b = create_test_user(db, email="cb_b@example.com")
    ca = create_test_company(db, a, slug="cb-a")
    cb = create_test_company(db, b, slug="cb-b")
    HotelConnectorService(ca.id, db).save_config(hotel_num=111, auth_access_token="t")
    HotelConnectorService(cb.id, db).save_config(hotel_num=222, auth_access_token="t")
    HotelConnectorService(ca.id, db)._upsert_order(111, "ORD1", _detail(order_num="ORD1"))
    HotelConnectorService(cb.id, db)._upsert_order(222, "ORD1", _detail(order_num="ORD1"))
    db.commit()

    msg = {"action": "ORDER_CHANGE",
           "reqMsg": json.dumps({"orderNum": "ORD1", "hotelNum": "111", "type": 3})}
    r = client.post("/api/v1/callbacks/ddll", json=_callback_body(callback_env, msg))
    assert r.status_code == 200 and r.json()["action"] == "cancelled"

    status_by_company = {
        o.company_id: o.status for o in db.query(HotelOrder).filter_by(order_num="ORD1")
    }
    assert status_by_company[ca.id] == 4   # cancelled for the owning tenant
    assert status_by_company[cb.id] == 3   # other tenant untouched


def test_callback_unknown_hotel_is_acknowledged_without_effect(client, callback_env):
    msg = {"action": "ORDER_CHANGE",
           "reqMsg": json.dumps({"orderNum": "Z", "hotelNum": "424242", "type": 1})}
    r = client.post("/api/v1/callbacks/ddll", json=_callback_body(callback_env, msg))
    assert r.status_code == 200 and r.json().get("handled") is False


# ---------------------------------------------------------------------------
# Token lifecycle: ticket -> componentAccessToken -> authAccessToken
# ---------------------------------------------------------------------------

class _TokenPlatform:
    """Fake of the two token endpoints; records how often each is hit."""

    def __init__(self, store_expire=7200):
        self.component_calls = 0
        self.store_calls = 0
        self.store_expire = store_expire

    async def request_component_token(self, *, ticket):
        self.component_calls += 1
        return {"componentAccessToken": f"comp-{self.component_calls}", "expire": 7200}

    async def request_store_token(self, *, component_access_token, hotel_num):
        self.store_calls += 1
        return {
            "authAccessToken": f"store-{self.store_calls}",
            "expire": self.store_expire,
            "authRefreshToken": "refresh-xyz",
            "ntwNum": str(hotel_num),
        }


@pytest.fixture()
def token_env(db, monkeypatch):
    from app.connectors.hotel import service as svc_mod

    monkeypatch.setattr(settings, "DDLL_APP_CODE", "1559616142200725504")
    monkeypatch.setattr(settings, "DDLL_APP_SECRET", "unit-test-secret")
    owner = create_test_user(db, email="tok_owner@example.com")
    company = create_test_company(db, owner, slug="tok-co")
    svc = svc_mod.HotelConnectorService(company.id, db)
    cfg = svc.save_config(hotel_num=34241741)
    platform = _TokenPlatform()
    monkeypatch.setattr(svc, "_app_client", lambda: platform)
    return svc, cfg, platform, svc_mod


@pytest.mark.asyncio
async def test_store_token_minted_from_ticket_and_encrypted(token_env, db):
    svc, cfg, platform, svc_mod = token_env
    svc_mod.store_ticket(db, "ticket-1")
    token = await svc.ensure_store_token(cfg)
    assert token == "store-1"
    assert (platform.component_calls, platform.store_calls) == (1, 1)

    stored = cfg.encrypted_credentials
    assert "store-1" not in stored and "refresh-xyz" not in stored   # encrypted at rest
    summary = svc.masked_config_summary()
    assert summary["token_mode"] == "auto" and summary["token_expires_at"]
    assert "store-1" not in json.dumps(summary, default=str)


@pytest.mark.asyncio
async def test_valid_store_token_is_reused_not_reminted(token_env, db):
    svc, cfg, platform, svc_mod = token_env
    svc_mod.store_ticket(db, "ticket-1")
    await svc.ensure_store_token(cfg)
    await svc.ensure_store_token(cfg)
    await svc.ensure_store_token(cfg)
    assert platform.store_calls == 1


@pytest.mark.asyncio
async def test_expiring_store_token_is_reminted(token_env, db):
    svc, cfg, platform, svc_mod = token_env
    platform.store_expire = 60            # inside the 300s refresh margin
    svc_mod.store_ticket(db, "ticket-1")
    first = await svc.ensure_store_token(cfg)
    second = await svc.ensure_store_token(cfg)
    assert first == "store-1" and second == "store-2"
    assert platform.component_calls == 1  # cached app credential reused


@pytest.mark.asyncio
async def test_missing_ticket_gives_actionable_error(token_env):
    from app.connectors.hotel.client import DdllApiError

    svc, cfg, platform, svc_mod = token_env
    with pytest.raises(DdllApiError) as exc:
        await svc.ensure_store_token(cfg)
    assert exc.value.code == "NO_TICKET" and "ticket" in exc.value.message
    assert platform.store_calls == 0


@pytest.mark.asyncio
async def test_manual_token_is_used_without_app_credentials(db, monkeypatch):
    from app.connectors.hotel import service as svc_mod

    monkeypatch.setattr(settings, "DDLL_APP_CODE", "")
    monkeypatch.setattr(settings, "DDLL_APP_SECRET", "")
    owner = create_test_user(db, email="manual_tok@example.com")
    company = create_test_company(db, owner, slug="manual-tok")
    svc = svc_mod.HotelConnectorService(company.id, db)
    cfg = svc.save_config(hotel_num=1, auth_access_token="manually-entered")
    assert await svc.ensure_store_token(cfg) == "manually-entered"
    assert svc.masked_config_summary()["token_mode"] == "manual"


def test_configure_without_token_is_allowed(client, db):
    owner = create_test_user(db, email="notoken@example.com")
    company = create_test_company(db, owner, slug="notoken-co")
    r = client.post(f"/api/v1/companies/{company.id}/connectors/hotel",
                    json={"hotel_num": 34241741}, headers=auth_headers(owner))
    assert r.status_code == 200 and r.json()["token_mode"] == "none"


def test_ticket_endpoint_is_platform_admin_only(client, db):
    admin = create_test_user(db, email="ticket_admin@example.com", is_platform_admin=True)
    user = create_test_user(db, email="ticket_user@example.com")
    assert client.post("/api/v1/admin/ddll/ticket", json={"ticket": "T"},
                       headers=auth_headers(user)).status_code == 403
    assert client.post("/api/v1/admin/ddll/ticket", json={"ticket": "T-ok"},
                       headers=auth_headers(admin)).status_code == 204
    from app.connectors.hotel.service import get_ticket
    assert get_ticket(db)["ticket"] == "T-ok"
