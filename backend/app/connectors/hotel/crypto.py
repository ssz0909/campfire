"""
Cryptography for the 订单来了 (Dingdanlai) open platform.

Algorithms were verified against the sample callback printed in the vendor's
API document (``订单来了API.docx``):

* Request signing  : RSA2 = SHA1withRSA (PKCS#1 v1.5) over the sorted
                     ``key=value`` pairs joined by ``&``; result is Base64.
* Callback verify  : same algorithm, verified with the *platform* public key
                     over ``appCode, timestamp, nonce, msg`` (msg = decrypted).
* Callback payload : AES-256-CBC, IV = first 16 bytes of the key,
                     PKCS#7 padding with a 32-byte block. Plaintext =
                     16 random bytes + 4-byte big-endian length + message.

Nothing in this module logs key material.
"""
from __future__ import annotations

import base64
import re
from functools import lru_cache
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

BACKEND_DIR = Path(__file__).resolve().parents[3]


class DdllCryptoError(Exception):
    """Raised for malformed keys, undecryptable payloads or bad signatures."""


def _strip_pem(text: str) -> bytes:
    body = re.sub(r"-----[^-]+-----|\s", "", text)
    try:
        return base64.b64decode(body, validate=True)
    except Exception as exc:  # noqa: BLE001
        raise DdllCryptoError("Key is not valid Base64/PEM") from exc


def signature_content(params: dict[str, str]) -> str:
    """Sorted ``k=v`` pairs joined with ``&`` (keys compared by code point)."""
    return "&".join(f"{k}={params[k]}" for k in sorted(params))


def load_private_key_der(path_or_body: str) -> bytes:
    """Accept a file path (relative to backend/) or the Base64 body itself."""
    candidate = Path(path_or_body)
    if not candidate.is_absolute():
        candidate = (BACKEND_DIR / path_or_body).resolve()
    if len(path_or_body) < 512 and candidate.is_file():
        return _strip_pem(candidate.read_text())
    return _strip_pem(path_or_body)


@lru_cache(maxsize=8)
def _private_key(der: bytes):
    try:
        return serialization.load_der_private_key(der, password=None)
    except Exception as exc:  # noqa: BLE001
        raise DdllCryptoError("Private key must be an unencrypted PKCS#8 RSA key") from exc


@lru_cache(maxsize=8)
def _public_key(der: bytes):
    try:
        return serialization.load_der_public_key(der)
    except Exception as exc:  # noqa: BLE001
        raise DdllCryptoError("Public key must be an X.509 SubjectPublicKeyInfo RSA key") from exc


def sign(content: str, private_key_der: bytes) -> str:
    key = _private_key(private_key_der)
    signature = key.sign(content.encode("utf-8"), padding.PKCS1v15(), hashes.SHA1())
    return base64.b64encode(signature).decode("ascii")


def verify(content: str, signature_b64: str, public_key_b64: str) -> bool:
    try:
        key = _public_key(_strip_pem(public_key_b64))
        key.verify(
            base64.b64decode(signature_b64),
            content.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA1(),
        )
        return True
    except (InvalidSignature, ValueError):
        return False


def aes_decrypt(encrypted_b64: str, aes_key_b64: str) -> str:
    """
    Decrypt a callback ``msg`` field and return the embedded message text.

    Layout (verified against the vendor sample)::

        AES-256-CBC, IV = key[:16]
        plaintext = 16 random bytes | 4-byte big-endian length | message | padding
        padding   = PKCS#7 with a 32-byte block (pad value == pad length, 1..32)
    """
    try:
        key = base64.b64decode(aes_key_b64)
        if len(key) != 32:
            raise DdllCryptoError("AES key must decode to 32 bytes")
        raw = base64.b64decode(encrypted_b64)
        if not raw or len(raw) % 16:
            raise DdllCryptoError("Ciphertext length is not a multiple of the block size")
        decryptor = Cipher(algorithms.AES(key), modes.CBC(key[:16])).decryptor()
        plain = decryptor.update(raw) + decryptor.finalize()

        pad = plain[-1]
        if not 1 <= pad <= 32 or pad > len(plain):
            raise DdllCryptoError("Invalid padding")
        if plain[-pad:] != bytes([pad]) * pad:
            raise DdllCryptoError("Invalid padding")
        body = plain[:-pad]

        if len(body) < 20:
            raise DdllCryptoError("Payload too short")
        length = int.from_bytes(body[16:20], "big")
        message = body[20 : 20 + length]
        if len(message) != length:
            raise DdllCryptoError("Declared message length exceeds payload")
        return message.decode("utf-8")
    except DdllCryptoError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise DdllCryptoError("Unable to decrypt message") from exc
