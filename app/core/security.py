"""
Security utilities: API key validation, LINE signature verification, etc.
"""

import hashlib
import hmac
import base64
import secrets
from typing import Optional

from fastapi import HTTPException, Security, Depends
from fastapi.security import APIKeyHeader

from app.core.config import get_settings


# --- LINE Signature Verification ---

def verify_line_signature(body: bytes, signature: str, channel_secret: str) -> bool:
    """
    Verify LINE webhook signature using HMAC-SHA256.

    Args:
        body: Raw request body bytes.
        signature: X-Line-Signature header value.
        channel_secret: LINE Channel Secret.

    Returns:
        True if signature is valid.
    """
    mac = hmac.new(
        channel_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    )
    expected = base64.b64encode(mac.digest()).decode("utf-8")
    return hmac.compare_digest(signature, expected)


# --- Vendor API Key Authentication ---

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_vendor_api_key(
    api_key: Optional[str] = Security(_api_key_header),
) -> str:
    """
    FastAPI dependency to verify vendor API key.

    Returns:
        The validated API key string.

    Raises:
        HTTPException: If key is missing or invalid.
    """
    settings = get_settings()
    if not api_key or not secrets.compare_digest(api_key, settings.vendor_api_key):
        raise HTTPException(status_code=401, detail="無效的 API 金鑰")
    return api_key


# --- Content Hash ---

def compute_sha256(data: bytes) -> str:
    """Compute SHA-256 hex digest of binary data."""
    return hashlib.sha256(data).hexdigest()
