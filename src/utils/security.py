"""Security helpers: secret masking, hashing, safe comparisons, SSRF guards."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import socket
import urllib.parse
from typing import Any

from cryptography import fernet

from exceptions import EncryptionError


def mask_secret(value: str | None, *, visible_chars: int = 4) -> str:
    """Mask a secret, keeping only the final few characters visible."""
    if not value:
        return "None"
    if len(value) <= visible_chars:
        return "*" * len(value)
    return f"{'*' * (len(value) - visible_chars)}{value[-visible_chars:]}"


def mask_dict(d: dict[str, Any], sensitive: set[str]) -> dict[str, Any]:
    """Return a copy of the dict with sensitive keys masked."""
    out = dict(d)
    for key in out:
        if key in sensitive or any(s in key.lower() for s in ("token", "secret", "password")):
            out[key] = "***"
    return out


def _hash(generic_hash: Any, key: str, msg: bytes) -> bytes:
    return generic_hash(key.encode(), msg)


def hash_credential(value: str, salt: str) -> str:
    """Deterministic HMAC-SHA256 of a credential for deduplication/lookup."""
    digest = hmac.new(salt.encode(), value.encode(), hashlib.sha256).digest()
    return digest.hex()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def base64url_encode_fernet(text: str) -> str:
    """Fernet-style base64url encode without padding."""
    import base64

    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def decrypt_fernet(token: bytes, keys: list[bytes]) -> bytes:
    """Decrypt a Fernet token trying each key (current first, then rotation keys)."""
    last_error: Exception | None = None
    for raw in keys:
        try:
            return fernet.Fernet(raw).decrypt(token)
        except Exception as exc:
            last_error = exc
    raise EncryptionError("credential decryption failed") from last_error


def is_private_ip(resolved_ip: str) -> bool:
    """Return True when an IP address is loopback/private/link-local (SSRF guard)."""
    try:
        addr = ipaddress.ip_address(resolved_ip)
    except ValueError:
        return True
    return addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved


def validate_target_url(url: str) -> str:
    """Validate an outbound webhook URL is http(s) and not SSRF-risky."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"unsupported URL scheme: {parsed.scheme!r}")
    host = parsed.hostname or ""
    if host in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("localhost targets are not allowed")
    try:
        resolved = socket.gethostbyname(host)
    except OSError as exc:
        raise ValueError(f"unresolvable host: {host}") from exc
    if is_private_ip(resolved):
        raise ValueError(f"private-network target blocked: {host}")
    return url
