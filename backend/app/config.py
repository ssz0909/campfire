from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Database
    DATABASE_URL: str = "postgresql://postgres:password@localhost:5432/aiops_db"

    # Inline execution works without a separate queue worker. Production can opt into Celery.
    TASK_EXECUTION_MODE: Literal["inline", "celery"] = "inline"
    EXECUTION_AUTOMATION_ENABLED: bool = True

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    SECRET_KEY: str = "change-me-to-a-secure-random-string-at-least-32-chars"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Storage
    STORAGE_BACKEND: Literal["local", "s3"] = "local"
    LOCAL_STORAGE_PATH: str = "/tmp/aiops_storage"
    S3_ENDPOINT_URL: str = ""
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_BUCKET_NAME: str = ""

    # LLM
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = ""
    LLM_MODEL: str = ""
    LLM_TIMEOUT_SECONDS: float = 300

    # Social publishing. Credentials are supplied by the platform operator after
    # registering approved applications with each provider.
    DOUYIN_CLIENT_ID: str = ""
    DOUYIN_CLIENT_SECRET: str = ""
    DOUYIN_REDIRECT_URI: str = ""
    DOUYIN_TOKEN_URL: str = "https://open.douyin.com/oauth/access_token/"
    WECHAT_CHANNELS_CLIENT_ID: str = ""
    WECHAT_CHANNELS_CLIENT_SECRET: str = ""
    WECHAT_CHANNELS_REDIRECT_URI: str = ""
    WECHAT_CHANNELS_TOKEN_URL: str = ""
    PUBLISHING_MOCK: bool = False
    WEB_BROWSER_HEADLESS: bool = False
    WEB_BROWSER_EXECUTABLE: str = ""

    # Video
    VIDEO_PROVIDER: Literal["mock", "seedance", "relay"] = "relay"
    SEEDANCE_API_KEY: str = ""
    VIDEO_BASE_URL: str = ""
    VIDEO_MODEL: str = ""
    VIDEO_API_KEY: str = ""
    VIDEO_STATUS_URL: str = ""
    VIDEO_POLL_SECONDS: float = 10
    VIDEO_TIMEOUT_SECONDS: int = 1800
    VIDEO_RESOLUTION: str = "720P"
    VIDEO_AUDIO: bool = True
    PUBLIC_BASE_URL: str = ""

    # Hotel connector: 订单来了 (Dingdanlai) open platform
    DDLL_BASE_URL: str = "https://open.dingdanll.com"
    DDLL_API_VERSION: str = "3.0"
    DDLL_APP_CODE: str = ""
    DDLL_APP_SECRET: str = ""
    # Our RSA2 private key (PKCS#8). Either a file path (relative paths resolve
    # against the backend directory) or the base64 body itself.
    DDLL_PRIVATE_KEY_PATH: str = ""
    DDLL_PRIVATE_KEY: str = ""
    # Provided by the platform: RSA public key for verifying callbacks, AES-256 key.
    DDLL_PLATFORM_PUBLIC_KEY: str = ""
    DDLL_AES_KEY: str = ""
    DDLL_HTTP_TIMEOUT_SECONDS: float = 20.0

    # Key used to encrypt third-party credentials at rest (Fernet). When empty a
    # key is derived from SECRET_KEY; set it explicitly in production.
    CREDENTIAL_ENCRYPTION_KEY: str = ""

    # Upload limits
    MAX_UPLOAD_SIZE_MB: int = 100
    ALLOWED_IMAGE_TYPES: str = "image/jpeg,image/png,image/gif,image/webp,image/svg+xml"
    ALLOWED_VIDEO_TYPES: str = "video/mp4,video/quicktime,video/x-msvideo,video/webm"
    ALLOWED_AUDIO_TYPES: str = "audio/mpeg,audio/wav,audio/x-wav"
    ALLOWED_DOC_TYPES: str = (
        "application/pdf,"
        "application/msword,"
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document,"
        "text/plain"
    )

    # Environment
    ENVIRONMENT: Literal["development", "production"] = "development"
    USE_MOCK_DATA: bool = True

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    @field_validator("USE_MOCK_DATA", mode="before")
    @classmethod
    def default_mock_data(cls, v: bool | str, info: object) -> bool:
        return v

    def get_allowed_image_types(self) -> list[str]:
        return [t.strip() for t in self.ALLOWED_IMAGE_TYPES.split(",") if t.strip()]

    def get_allowed_video_types(self) -> list[str]:
        return [t.strip() for t in self.ALLOWED_VIDEO_TYPES.split(",") if t.strip()]

    def get_allowed_doc_types(self) -> list[str]:
        return [t.strip() for t in self.ALLOWED_DOC_TYPES.split(",") if t.strip()]

    def get_all_allowed_types(self) -> list[str]:
        return (
            self.get_allowed_image_types()
            + self.get_allowed_video_types()
            + [t.strip() for t in self.ALLOWED_AUDIO_TYPES.split(',') if t.strip()]
            + self.get_allowed_doc_types()
        )

    def get_cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    def mask_secret(self, value: str) -> str:
        """Return first 8 chars + *** for logging."""
        if not value:
            return "***"
        return value[:8] + "***"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
