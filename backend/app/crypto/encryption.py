import hashlib
import hmac
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class EncryptionService:
    def __init__(self, encryption_key: bytes, lookup_key: bytes) -> None:
        if len(encryption_key) != 32:
            raise ValueError("AES-256-GCM requires a 32-byte key")
        self._aes = AESGCM(encryption_key)
        self._lookup_key = lookup_key

    def encrypt(self, plaintext: str, *, context: bytes = b"payseal-account-v1") -> bytes:
        nonce = os.urandom(12)
        return nonce + self._aes.encrypt(nonce, plaintext.encode(), context)

    def decrypt(self, ciphertext: bytes, *, context: bytes = b"payseal-account-v1") -> str:
        return self._aes.decrypt(ciphertext[:12], ciphertext[12:], context).decode()

    def lookup_hash(self, value: str) -> str:
        normalized = "".join(value.split())
        return hmac.new(self._lookup_key, normalized.encode(), hashlib.sha256).hexdigest()

    def mask(self, value: str) -> str:
        return "*" * max(6, len(value) - 4) + value[-4:]
