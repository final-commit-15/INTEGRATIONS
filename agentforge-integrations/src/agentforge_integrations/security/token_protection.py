import time
from typing import Any

import jwt

from ..core.exceptions import AuthenticationError


class TokenProtection:
    """Utilities for JWT creation/validation for internal agent communication."""

    def __init__(self, secret_key: str, algorithm: str = "HS256", expiry_seconds: int = 3600):
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.expiry_seconds = expiry_seconds

    def create_token(self, payload: dict[str, Any], expiry: int | None = None) -> str:
        data = payload.copy()
        exp = expiry or (time.time() + self.expiry_seconds)
        data["exp"] = int(exp)
        return jwt.encode(data, self.secret_key, algorithm=self.algorithm)

    def validate_token(self, token: str) -> dict[str, Any]:
        try:
            return jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
        except jwt.ExpiredSignatureError:
            raise AuthenticationError("Token expired")
        except jwt.InvalidTokenError as e:
            raise AuthenticationError(f"Invalid token: {e}")