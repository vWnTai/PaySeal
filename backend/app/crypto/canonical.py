import hashlib
import json
from typing import Any


def canonicalize(value: Any) -> bytes:
    """Deterministic UTF-8 JSON for PaySeal's integer/string/bool/null value domain."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
