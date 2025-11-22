"""Simple symmetric secret obfuscation helpers.

These helpers are intended for protecting sensitive settings (API keys, tokens)
when stored at rest in the database. They are **not** a replacement for a
proper secrets manager, but they avoid storing secrets in plaintext.

Implementation notes:
- We derive a key from Config.SESSION_SECRET using SHA-256.
- We XOR the plaintext bytes with the key and base64-encode the result.
- Decryption reverses this process; if anything fails we fall back to returning
  the original value.
"""

from __future__ import annotations

import base64
import hashlib
from typing import Optional

from config import Config
from utils.logger import get_logger

logger = get_logger(__name__)

_KEY_CACHE: Optional[bytes] = None


def _get_key() -> Optional[bytes]:
    """Derive a symmetric key from SESSION_SECRET.

    Returns None if SESSION_SECRET is not configured, in which case we fall
    back to a weaker base64-only obfuscation.
    """

    global _KEY_CACHE
    if _KEY_CACHE is not None:
        return _KEY_CACHE

    secret = Config.SESSION_SECRET or ""
    if not secret:
        return None

    _KEY_CACHE = hashlib.sha256(secret.encode("utf-8")).digest()
    return _KEY_CACHE


def encrypt_secret(plain: str) -> str:
    """Encrypt/obfuscate a secret string for storage.

    If no SESSION_SECRET is configured, this falls back to urlsafe base64 of
    the plaintext. This is mainly to avoid breaking in dev environments.
    """

    if plain is None:
        return ""

    try:
        plain_bytes = plain.encode("utf-8")
    except Exception:
        # As a last resort, coerce to str and encode
        plain_bytes = str(plain).encode("utf-8", errors="ignore")

    key = _get_key()
    if not key:
        return base64.urlsafe_b64encode(plain_bytes).decode("ascii")

    cipher = bytes(b ^ key[i % len(key)] for i, b in enumerate(plain_bytes))
    return base64.urlsafe_b64encode(cipher).decode("ascii")


def decrypt_secret(encoded: str) -> str:
    """Decrypt a secret previously returned by encrypt_secret.

    If decoding or decryption fails, the original encoded string is returned.
    """

    if not encoded:
        return ""

    try:
        data = base64.urlsafe_b64decode(encoded.encode("ascii"))
    except Exception:
        # Not base64 – assume plaintext
        return encoded

    key = _get_key()
    if not key:
        # No key; treat decoded bytes as plaintext
        try:
            return data.decode("utf-8")
        except Exception:
            return encoded

    try:
        plain_bytes = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
        return plain_bytes.decode("utf-8")
    except Exception:
        logger.error("Failed to decrypt secret; returning original encoded value")
        return encoded
