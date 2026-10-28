from __future__ import annotations

import base64
import json
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import (
    decode_dss_signature,
    encode_dss_signature,
)

from app.crypto.canonical import canonicalize


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def public_key_to_jwk(key: ec.EllipticCurvePublicKey, kid: str) -> dict[str, str]:
    numbers = key.public_numbers()
    return {
        "kty": "EC",
        "crv": "P-256",
        "use": "sig",
        "alg": "ES256",
        "kid": kid,
        "x": b64url(numbers.x.to_bytes(32, "big")),
        "y": b64url(numbers.y.to_bytes(32, "big")),
    }


def jwk_to_public_key(jwk: dict[str, Any]) -> ec.EllipticCurvePublicKey:
    if jwk.get("kty") != "EC" or jwk.get("crv") != "P-256":
        raise ValueError("unsupported JWK")
    numbers = ec.EllipticCurvePublicNumbers(
        int.from_bytes(b64url_decode(jwk["x"]), "big"),
        int.from_bytes(b64url_decode(jwk["y"]), "big"),
        ec.SECP256R1(),
    )
    return numbers.public_key()


def sign_compact(
    payload: dict[str, Any], private_key: ec.EllipticCurvePrivateKey, kid: str, typ: str
) -> str:
    header = {"alg": "ES256", "kid": kid, "typ": typ}
    encoded_header = b64url(canonicalize(header))
    encoded_payload = b64url(canonicalize(payload))
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    der = private_key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    raw = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return f"{encoded_header}.{encoded_payload}.{b64url(raw)}"


def verify_compact(
    token: str, public_key: ec.EllipticCurvePublicKey, expected_typ: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("invalid compact JWS")
    header = json.loads(b64url_decode(parts[0]))
    if header.get("alg") != "ES256" or header.get("typ") != expected_typ:
        raise ValueError("unexpected JWS protected header")
    raw = b64url_decode(parts[2])
    if len(raw) != 64:
        raise ValueError("invalid ES256 signature size")
    der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
    public_key.verify(der, f"{parts[0]}.{parts[1]}".encode("ascii"), ec.ECDSA(hashes.SHA256()))
    return header, json.loads(b64url_decode(parts[1]))
