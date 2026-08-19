from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Any

from fastapi import Header, HTTPException, Request, status


@dataclass(frozen=True)
class AuthContext:
    """The verified identity carried into an API request.

    The application does not expose a login endpoint. Tokens are issued by the
    selected identity provider in a deployed environment. ``issue_token`` is
    deliberately a small local/test helper, not a replacement for that provider.
    """

    user_id: int
    role: str
    school_id: str | None
    expires_at: int


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def issue_token(
    *,
    user_id: int,
    secret: str,
    role: str = "student",
    school_id: str | None = None,
    expires_at: int | None = None,
) -> str:
    """Create a compact HMAC token for deterministic local tests.

    Production callers should pass tokens issued by the configured identity
    provider. Keeping this helper here makes authorization tests independent of
    network services without weakening the request-time signature check.
    """

    if user_id < 1 or not secret:
        raise ValueError("user_id and secret are required")
    payload = {
        "sub": str(user_id),
        "role": role,
        "school_id": school_id,
        "exp": int(expires_at if expires_at is not None else time.time() + 3600),
    }
    body = _encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{_encode(signature)}"


def verify_token(token: str, secret: str, *, now: int | None = None) -> AuthContext:
    try:
        body, supplied_signature = token.split(".", 1)
        expected_signature = _encode(
            hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise ValueError("invalid signature")
        payload: Any = json.loads(_decode(body).decode("utf-8"))
        user_id = int(payload["sub"])
        role = str(payload["role"])
        expires_at = int(payload["exp"])
        school_id = payload.get("school_id")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, UnicodeDecodeError, base64.binascii.Error) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token") from exc

    if user_id < 1 or not role or expires_at <= int(time.time() if now is None else now):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication token expired")
    return AuthContext(user_id=user_id, role=role, school_id=school_id, expires_at=expires_at)


def get_auth_context(
    request: Request,
    authorization: str | None = Header(default=None),
) -> AuthContext:
    secret = str(getattr(request.app.state, "auth_secret", "") or os.getenv("AUTH_SECRET", "")).strip()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured",
        )
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer authentication is required")
    return verify_token(authorization[7:].strip(), secret)
