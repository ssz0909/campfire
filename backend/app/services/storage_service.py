from __future__ import annotations

import io
import os
import uuid
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from app.config import settings
from app.core.security import generate_signed_url


class StorageService:
    """
    Unified file storage service supporting local filesystem and S3-compatible backends.
    """

    def __init__(self, backend: str = "local") -> None:
        self.backend = backend
        if backend == "s3":
            self._s3 = boto3.client(
                "s3",
                endpoint_url=settings.S3_ENDPOINT_URL or None,
                aws_access_key_id=settings.S3_ACCESS_KEY,
                aws_secret_access_key=settings.S3_SECRET_KEY,
            )
            self._bucket = settings.S3_BUCKET_NAME
        else:
            self._local_root = Path(settings.LOCAL_STORAGE_PATH)
            self._local_root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def upload_file(
        self,
        file_data: bytes,
        key: str,
        content_type: str,
    ) -> str:
        """Upload file_data under key and return a public or internal URL."""
        if self.backend == "s3":
            return self._s3_upload(file_data, key, content_type)
        return self._local_upload(file_data, key, content_type)

    def delete_file(self, key: str) -> None:
        """Delete a file by its storage key."""
        if self.backend == "s3":
            self._s3_delete(key)
        else:
            self._local_delete(key)

    def generate_presigned_url(self, key: str, expires_in: int = 3600) -> str:
        """
        Generate a temporary URL for private file access.
        S3: uses boto3 presigned URL.
        Local: returns a signed JWT URL served by the app.
        """
        if self.backend == "s3":
            return self._s3_presigned(key, expires_in)
        return generate_signed_url(key, expires_in)

    def get_file(self, key: str) -> bytes:
        """Retrieve raw file bytes (local backend only; S3 uses presigned URLs)."""
        if self.backend == "s3":
            response = self._s3.get_object(Bucket=self._bucket, Key=key)
            return response["Body"].read()
        path = self._local_root / key
        with open(path, "rb") as f:
            return f.read()

    # ------------------------------------------------------------------
    # Local backend
    # ------------------------------------------------------------------

    def _local_upload(self, file_data: bytes, key: str, content_type: str) -> str:
        path = self._local_root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            f.write(file_data)
        # Return an internal reference path; the API layer converts to a URL
        return f"/files/{key}"

    def _local_delete(self, key: str) -> None:
        path = self._local_root / key
        if path.exists():
            path.unlink()

    # ------------------------------------------------------------------
    # S3 backend
    # ------------------------------------------------------------------

    def _s3_upload(self, file_data: bytes, key: str, content_type: str) -> str:
        self._s3.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=file_data,
            ContentType=content_type,
        )
        if settings.S3_ENDPOINT_URL:
            return f"{settings.S3_ENDPOINT_URL}/{self._bucket}/{key}"
        return f"https://{self._bucket}.s3.amazonaws.com/{key}"

    def _s3_delete(self, key: str) -> None:
        try:
            self._s3.delete_object(Bucket=self._bucket, Key=key)
        except ClientError:
            pass  # Already gone

    def _s3_presigned(self, key: str, expires_in: int) -> str:
        return self._s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_in,
        )
