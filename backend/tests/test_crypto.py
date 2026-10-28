import pytest
from app.crypto.canonical import canonicalize
from app.crypto.jws import sign_compact, verify_compact
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ec


def test_canonical_json_is_deterministic():
    assert canonicalize({"b": 2, "a": {"z": False, "x": "đ"}}) == canonicalize(
        {"a": {"x": "đ", "z": False}, "b": 2}
    )


def test_es256_valid_wrong_key_and_modified_payload():
    key = ec.generate_private_key(ec.SECP256R1())
    payload = {"amount_minor": 28_500_000, "account_number": "123456789"}
    token = sign_compact(payload, key, "test-key", "payseal+jws")
    header, decoded = verify_compact(token, key.public_key(), "payseal+jws")
    assert header["alg"] == "ES256" and decoded == payload
    with pytest.raises(InvalidSignature):
        verify_compact(token, ec.generate_private_key(ec.SECP256R1()).public_key(), "payseal+jws")
    parts = token.split(".")
    altered = sign_compact({**payload, "amount_minor": 1}, key, "test-key", "payseal+jws")
    forged = f"{altered.split('.')[0]}.{altered.split('.')[1]}.{parts[2]}"
    with pytest.raises(InvalidSignature):
        verify_compact(forged, key.public_key(), "payseal+jws")
