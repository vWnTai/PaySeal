from __future__ import annotations

import base64
from functools import cached_property
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    environment: str = "development"
    database_url: str = "sqlite:///./payseal.db"
    jwt_secret: str = "dev-only-jwt-secret-change-me-32-bytes"
    jwt_access_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 14
    refresh_token_secret: str = "dev-only-refresh-token-pepper-change-me"
    refresh_cookie_secure: bool = False
    account_encryption_key: str = ""
    account_lookup_hmac_key: str = "dev-only-hmac-key-change-me-32-bytes"
    key_encryption_secret: str = "dev-only-key-encryption-change-me"
    payseal_root_key_path: str = "./.keys/root-private.pem.enc"
    payseal_root_public_key_path: str = "./.keys/root-public.pem"
    signing_key_directory: str = "./.keys/organizations"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "payseal_minio"
    minio_secret_key: str = "payseal_minio_dev_secret"
    minio_bucket: str = "payseal-documents"
    minio_secure: bool = False
    public_verify_base_url: str = "http://localhost:3000/r"
    cors_origins: str = "http://localhost:3000"
    trusted_hosts: str = "localhost,127.0.0.1,testserver"
    max_pdf_bytes: int = 10 * 1024 * 1024
    mfa_recent_window_seconds: int = 300
    transfer_mode: Literal["disabled", "sandbox", "live"] = "sandbox"
    transfer_webhook_secret: str = ""
    max_business_document_bytes: int = 5 * 1024 * 1024
    payments_live_enabled: bool = False
    public_app_url: str = ""
    max_live_transfer_amount: int = 1_000_000

    @field_validator("transfer_webhook_secret")
    @classmethod
    def validate_webhook_secret(cls, value: str) -> str:
        if value and len(value.encode()) < 32:
            raise ValueError("TRANSFER_WEBHOOK_SECRET must be at least 32 bytes")
        return value

    @field_validator(
        "jwt_secret",
        "refresh_token_secret",
        "account_lookup_hmac_key",
        "key_encryption_secret",
    )
    @classmethod
    def validate_secret(cls, value: str) -> str:
        if len(value.encode()) < 32:
            raise ValueError("security secrets must be at least 32 bytes")
        return value

    @cached_property
    def account_key_bytes(self) -> bytes:
        if self.account_encryption_key:
            try:
                key = base64.urlsafe_b64decode(
                    self.account_encryption_key + "=" * (-len(self.account_encryption_key) % 4)
                )
            except Exception as exc:
                raise ValueError("ACCOUNT_ENCRYPTION_KEY must be base64") from exc
            if len(key) != 32:
                raise ValueError("ACCOUNT_ENCRYPTION_KEY must decode to 32 bytes")
            return key
        if self.environment == "production":
            raise ValueError("ACCOUNT_ENCRYPTION_KEY is required in production")
        import hashlib

        return hashlib.sha256(b"payseal-local-account-key").digest()

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def trusted_host_list(self) -> list[str]:
        return [item.strip() for item in self.trusted_hosts.split(",") if item.strip()]


settings = Settings()
