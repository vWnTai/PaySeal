from __future__ import annotations

import hashlib
import os
from abc import ABC, abstractmethod
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.crypto.jws import public_key_to_jwk


class SigningProvider(ABC):
    @abstractmethod
    def create_key(self, key_id: str) -> dict[str, str]: ...
    @abstractmethod
    def sign(self, key_id: str, data: bytes) -> bytes: ...
    @abstractmethod
    def get_public_key(self, key_id: str) -> ec.EllipticCurvePublicKey: ...
    @abstractmethod
    def rotate_key(self, old_key_id: str, new_key_id: str) -> dict[str, str]: ...
    @abstractmethod
    def revoke_key(self, key_id: str) -> None: ...


class LocalSigningProvider(SigningProvider):
    """Development provider. Exportable keys are encrypted at rest, outside the DB."""

    def __init__(self, directory: str, wrapping_secret: str) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._key = hashlib.sha256(wrapping_secret.encode()).digest()

    def _path(self, key_id: str) -> Path:
        safe = "".join(c for c in key_id if c.isalnum() or c in "-_")
        if safe != key_id:
            raise ValueError("unsafe key id")
        return self.directory / f"{safe}.pem.enc"

    def create_key(self, key_id: str) -> dict[str, str]:
        path = self._path(key_id)
        if path.exists():
            raise ValueError("key already exists")
        key = ec.generate_private_key(ec.SECP256R1())
        pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        nonce = os.urandom(12)
        path.write_bytes(nonce + AESGCM(self._key).encrypt(nonce, pem, key_id.encode()))
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return public_key_to_jwk(key.public_key(), key_id)

    def _private(self, key_id: str) -> ec.EllipticCurvePrivateKey:
        raw = self._path(key_id).read_bytes()
        pem = AESGCM(self._key).decrypt(raw[:12], raw[12:], key_id.encode())
        key = serialization.load_pem_private_key(pem, password=None)
        if not isinstance(key, ec.EllipticCurvePrivateKey):
            raise TypeError("not an EC private key")
        return key

    def sign(self, key_id: str, data: bytes) -> bytes:
        return self._private(key_id).sign(data, ec.ECDSA(hashes.SHA256()))

    def get_private_key(self, key_id: str) -> ec.EllipticCurvePrivateKey:
        return self._private(key_id)

    def get_public_key(self, key_id: str) -> ec.EllipticCurvePublicKey:
        return self._private(key_id).public_key()

    def rotate_key(self, old_key_id: str, new_key_id: str) -> dict[str, str]:
        return self.create_key(new_key_id)

    def revoke_key(self, key_id: str) -> None:
        # Metadata revocation is authoritative; key material remains for audit/verification.
        if not self._path(key_id).exists():
            raise FileNotFoundError(key_id)


class RootAuthority:
    def __init__(self, private_path: str, public_path: str, wrapping_secret: str) -> None:
        self.private_path = Path(private_path)
        self.public_path = Path(public_path)
        self.private_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._key = hashlib.sha256((wrapping_secret + ":root").encode()).digest()

    def ensure(self) -> None:
        if self.private_path.exists() and self.public_path.exists():
            return
        private = ec.generate_private_key(ec.SECP256R1())
        pem = private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        nonce = os.urandom(12)
        self.private_path.write_bytes(
            nonce + AESGCM(self._key).encrypt(nonce, pem, b"payseal-root")
        )
        self.public_path.write_bytes(
            private.public_key().public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )

    def private_key(self) -> ec.EllipticCurvePrivateKey:
        self.ensure()
        raw = self.private_path.read_bytes()
        key = serialization.load_pem_private_key(
            AESGCM(self._key).decrypt(raw[:12], raw[12:], b"payseal-root"),
            password=None,
        )
        assert isinstance(key, ec.EllipticCurvePrivateKey)
        return key

    def public_key(self) -> ec.EllipticCurvePublicKey:
        self.ensure()
        key = serialization.load_pem_public_key(self.public_path.read_bytes())
        assert isinstance(key, ec.EllipticCurvePublicKey)
        return key
