"""Compatibility wrappers for the independently authenticated PMS web client."""
from app.connectors.hotel.web_client import DddWebClient, DddWebError, aes_encrypt

DddWebLoginError = DddWebError
_aes_encrypt = aes_encrypt


async def web_login(phone: str, password: str, *, timeout: float = 20.0):
    return await DddWebClient(timeout=timeout).login(phone, password)


async def web_change_ntw(token, uid, ntw_num, ntw_id, *, timeout=20.0):
    return await DddWebClient(token=token, uid=uid, ntw_num=ntw_num, timeout=timeout).select_store(ntw_id)
