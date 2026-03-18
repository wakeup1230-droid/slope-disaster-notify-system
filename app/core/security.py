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


# --- Admin Token (HMAC-SHA256 + Time Expiry) ---

def generate_admin_token(user_id: str, secret: str, expires_in: int = 3600) -> str:
    """
    Generate an HMAC-SHA256 admin token for web management page access.

    Token format: base64url(json_payload).signature
    Payload: {"uid": user_id, "exp": unix_timestamp}

    Args:
        user_id: LINE User ID of the manager.
        secret: HMAC secret key (typically line_channel_secret).
        expires_in: Token lifetime in seconds (default: 3600 = 1 hour).

    Returns:
        URL-safe token string.
    """
    import json
    import time

    exp = int(time.time()) + expires_in
    payload = json.dumps({"uid": user_id, "exp": exp}, separators=(",", ":"))
    payload_b64 = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("utf-8").rstrip("=")
    sig = hmac.new(secret.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def verify_admin_token(token: str, secret: str) -> Optional[str]:
    """
    Verify an HMAC-SHA256 admin token and return the user_id if valid.

    Args:
        token: The token string from URL query parameter.
        secret: HMAC secret key (must match generation key).

    Returns:
        user_id string if token is valid and not expired, None otherwise.
    """
    import json
    import time

    if not token or "." not in token:
        return None

    try:
        payload_b64, sig = token.rsplit(".", 1)
        # Verify signature first
        expected_sig = hmac.new(
            secret.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None

        # Decode payload
        # Restore base64 padding
        padded = payload_b64 + "=" * (4 - len(payload_b64) % 4)
        payload_json = base64.urlsafe_b64decode(padded).decode("utf-8")
        payload = json.loads(payload_json)

        # Check expiry
        if int(time.time()) > payload.get("exp", 0):
            return None

        return payload.get("uid")
    except (ValueError, KeyError, json.JSONDecodeError, Exception):
        return None
