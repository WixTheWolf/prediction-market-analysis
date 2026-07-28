"""Authenticated Kalshi request signing.

Implements the documented RSA-PSS/SHA-256 scheme. Secrets are loaded from
environment variables or a mounted PEM file and are never written to logs.
"""

from __future__ import annotations

import base64
import os
import time
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


@dataclass(frozen=True)
class KalshiCredentials:
    key_id: str
    private_key: rsa.RSAPrivateKey

    @classmethod
    def from_environment(cls) -> "KalshiCredentials":
        key_id = os.getenv("KALSHI_API_KEY_ID", "").strip()
        inline_pem = os.getenv("KALSHI_PRIVATE_KEY_PEM", "").replace("\\n", "\n").strip()
        key_path = os.getenv("KALSHI_PRIVATE_KEY_PATH", "").strip()
        if not key_id:
            raise RuntimeError("KALSHI_API_KEY_ID is required")
        if inline_pem:
            pem = inline_pem.encode()
        elif key_path:
            pem = Path(key_path).read_bytes()
        else:
            raise RuntimeError("KALSHI_PRIVATE_KEY_PEM or KALSHI_PRIVATE_KEY_PATH is required")
        key = serialization.load_pem_private_key(pem, password=None)
        if not isinstance(key, rsa.RSAPrivateKey):
            raise TypeError("Kalshi private key must be RSA")
        return cls(key_id=key_id, private_key=key)


def sign_request(credentials: KalshiCredentials, method: str, path: str, timestamp_ms: str | None = None) -> dict[str, str]:
    timestamp = timestamp_ms or str(int(time.time() * 1000))
    clean_path = path.split("?", 1)[0]
    message = f"{timestamp}{method.upper()}{clean_path}".encode()
    signature = credentials.private_key.sign(
        message,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )
    return {
        "KALSHI-ACCESS-KEY": credentials.key_id,
        "KALSHI-ACCESS-TIMESTAMP": timestamp,
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode(),
        "Content-Type": "application/json",
    }
