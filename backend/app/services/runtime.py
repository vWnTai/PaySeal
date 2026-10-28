from functools import lru_cache

from app.core.config import settings
from app.crypto.encryption import EncryptionService
from app.crypto.signing import LocalSigningProvider, RootAuthority


@lru_cache
def encryption_service() -> EncryptionService:
    return EncryptionService(settings.account_key_bytes, settings.account_lookup_hmac_key.encode())


@lru_cache
def signing_provider() -> LocalSigningProvider:
    return LocalSigningProvider(settings.signing_key_directory, settings.key_encryption_secret)


@lru_cache
def root_authority() -> RootAuthority:
    return RootAuthority(
        settings.payseal_root_key_path,
        settings.payseal_root_public_key_path,
        settings.key_encryption_secret,
    )
