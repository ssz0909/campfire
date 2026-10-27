from __future__ import annotations

import io
import mimetypes
import os
import uuid
from pathlib import Path

try:
    import magic
except ImportError:
    magic = None

from app.config import settings


def detect_mime_type(file_data: bytes) -> str:
    """Detect MIME type from actual file bytes (magic bytes), not extension."""
    if magic is not None:
        try:
            return magic.from_buffer(file_data, mime=True)
        except ImportError:
            pass

    signatures = (
        (b"\xff\xd8\xff", "image/jpeg"),
        (b"\x89PNG\r\n\x1a\n", "image/png"),
        (b"GIF87a", "image/gif"),
        (b"GIF89a", "image/gif"),
        (b"%PDF-", "application/pdf"),
        (b"ID3", "audio/mpeg"),
        (b"fLaC", "audio/flac"),
        (b"OggS", "audio/ogg"),
        (b"\x1aE\xdf\xa3", "video/webm"),
        (b"RIFF", "application/octet-stream"),
        (b"PK\x03\x04", "application/zip"),
    )
    for signature, mime_type in signatures:
        if file_data.startswith(signature):
            if mime_type == "application/octet-stream" and file_data[8:12] == b"AVI ":
                return "video/x-msvideo"
            if mime_type == "application/octet-stream" and file_data[8:12] == b"WEBP":
                return "image/webp"
            if mime_type == "application/octet-stream" and file_data[8:12] == b"WAVE":
                return "audio/wav"
            if mime_type == "application/zip":
                try:
                    import zipfile
                    with zipfile.ZipFile(io.BytesIO(file_data)) as archive:
                        if "word/document.xml" in archive.namelist():
                            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                except (OSError, zipfile.BadZipFile):
                    pass
            return mime_type

    if len(file_data) >= 12 and file_data[4:8] == b"ftyp":
        brand = file_data[8:12]
        return "video/quicktime" if brand in (b"qt  ",) else "video/mp4"

    try:
        text = file_data.decode("utf-8")
        if "<svg" in text[:1024].lower():
            return "image/svg+xml"
        if "\x00" not in text:
            return "text/plain"
    except UnicodeDecodeError:
        pass
    return "application/octet-stream"


def validate_file_type(
    file_data: bytes, claimed_content_type: str, allowed_types: list[str]
) -> tuple[bool, str]:
    """
    Validate file using magic bytes.
    Returns (is_valid, actual_mime_type).
    """
    actual_mime = detect_mime_type(file_data)

    # Some MIME types have aliases; normalise
    normalised = _normalise_mime(actual_mime)
    allowed_normalised = [_normalise_mime(t) for t in allowed_types]

    if normalised not in allowed_normalised:
        return False, actual_mime
    return True, actual_mime


def _normalise_mime(mime: str) -> str:
    """Normalise common MIME aliases."""
    aliases: dict[str, str] = {
        "image/jpg": "image/jpeg",
        "video/mpeg": "video/mp4",
    }
    return aliases.get(mime, mime)


def classify_asset_type(mime_type: str) -> str:
    """Map MIME type to asset_type string."""
    if mime_type.startswith("image/"):
        return "image"
    if mime_type.startswith("video/"):
        return "video"
    if mime_type.startswith("audio/"):
        return "audio"
    if mime_type in (
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
    ):
        return "document"
    return "other"


def generate_storage_key(
    company_id: uuid.UUID,
    asset_type: str,
    original_filename: str,
) -> str:
    """Generate a unique, namespaced storage key."""
    ext = Path(original_filename).suffix.lower()
    unique_id = uuid.uuid4().hex
    return f"companies/{company_id}/{asset_type}/{unique_id}{ext}"


def safe_filename(filename: str) -> str:
    """Strip path traversal components and dangerous chars from a filename."""
    name = os.path.basename(filename)
    return "".join(c for c in name if c.isalnum() or c in "._- ")[:255]
