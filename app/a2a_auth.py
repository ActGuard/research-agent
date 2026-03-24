"""HMAC authentication middleware for the A2A JSON-RPC endpoint."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "a2a_auth.json"

REQUIRED_HEADERS = [
    "x-a2a-timestamp",
    "x-a2a-nonce",
    "x-a2a-content-sha256",
    "x-a2a-signature",
    "x-a2a-key-id",
]


class NonceCache:
    """In-memory nonce store with lazy expiry purge."""

    def __init__(self, ttl: int) -> None:
        self._ttl = ttl
        self._seen: dict[str, float] = {}

    def _purge(self) -> None:
        now = time.time()
        self._seen = {n: exp for n, exp in self._seen.items() if exp > now}

    def check_and_store(self, nonce: str) -> bool:
        """Return True if nonce is fresh (not replayed). Stores it on success."""
        self._purge()
        if nonce in self._seen:
            return False
        self._seen[nonce] = time.time() + self._ttl
        return True


def load_auth_config() -> dict[str, Any]:
    """Load and validate auth config from disk + environment."""
    raw = json.loads(CONFIG_PATH.read_text())

    required_keys = {
        "enabled": bool,
        "timestamp_skew_seconds": int,
        "nonce_ttl_seconds": int,
        "secret_env": str,
        "key_id": str,
        "allowed_method": str,
    }
    for key, expected_type in required_keys.items():
        if key not in raw:
            raise ValueError(f"a2a_auth config missing key: {key}")
        if not isinstance(raw[key], expected_type):
            raise TypeError(f"a2a_auth config key '{key}' must be {expected_type.__name__}")

    secret = os.environ.get(raw["secret_env"], "")
    if not secret:
        raise ValueError(
            f"Environment variable '{raw['secret_env']}' is not set or empty"
        )

    raw["_secret"] = secret.encode()
    raw["_nonce_cache"] = NonceCache(raw["nonce_ttl_seconds"])
    return raw


class HMACAuthMiddleware(BaseHTTPMiddleware):
    """Verify HMAC signatures on POST / requests."""

    def __init__(self, app: Any, auth_config: dict[str, Any]) -> None:
        super().__init__(app)
        self.cfg = auth_config

    async def dispatch(self, request: Request, call_next):  # noqa: ANN001
        if request.method != "POST" or request.url.path != "/":
            return await call_next(request)

        if not self.cfg["enabled"]:
            return await call_next(request)

        # 1. Check required headers
        for hdr in REQUIRED_HEADERS:
            if hdr not in request.headers:
                return _err(401, "missing_header", f"Missing header: {hdr}")

        # 2. Key-ID
        if request.headers["x-a2a-key-id"] != self.cfg["key_id"]:
            return _err(401, "invalid_key_id", "Unknown key ID")

        # 3. Timestamp skew
        try:
            ts = int(request.headers["x-a2a-timestamp"])
        except ValueError:
            return _err(401, "invalid_timestamp", "Timestamp must be an integer")
        if abs(time.time() - ts) > self.cfg["timestamp_skew_seconds"]:
            return _err(401, "timestamp_skew", "Timestamp outside acceptable window")

        # 4. Content SHA-256
        body = await request.body()
        expected_hash = hashlib.sha256(body).hexdigest()
        if not hmac.compare_digest(expected_hash, request.headers["x-a2a-content-sha256"]):
            return _err(401, "content_hash_mismatch", "Content SHA-256 does not match body")

        # 5. Signature verification
        nonce = request.headers["x-a2a-nonce"]
        host = request.headers.get("host", "")
        canonical = (
            f"{request.method}\n{host}\n{request.url.path}\n"
            f"{ts}\n{nonce}\n{expected_hash}"
        )
        computed = "v1=" + hmac.new(
            self.cfg["_secret"], canonical.encode(), hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(computed, request.headers["x-a2a-signature"]):
            return _err(401, "invalid_signature", "HMAC signature verification failed")

        # 6. Nonce replay
        nonce_cache: NonceCache = self.cfg["_nonce_cache"]
        if not nonce_cache.check_and_store(nonce):
            return _err(401, "nonce_replay", "Nonce has already been used")

        # 7. Parse JSON and check method
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            return _err(400, "invalid_json", "Request body is not valid JSON")

        if payload.get("method") != self.cfg["allowed_method"]:
            return _err(403, "method_not_allowed", f"Only '{self.cfg['allowed_method']}' is permitted")

        return await call_next(request)


def _err(status: int, error: str, detail: str) -> JSONResponse:
    return JSONResponse({"error": error, "detail": detail}, status_code=status)
