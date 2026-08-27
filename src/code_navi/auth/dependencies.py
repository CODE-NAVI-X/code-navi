"""FastAPI dependencies for current principal and CSRF validation."""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from ..db import get_db
from .models import AuthSession, Principal, User
from .security import hash_token
from .settings import session_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CurrentPrincipal:
    """Resolved identity attached to the current request."""

    principal_id: str
    user_id: str | None
    mode: str  # "guest" | "authenticated"
    email_verified: bool
    session_id: str


def _resolve_session(
    request: Request,
    db: Session,
) -> tuple[AuthSession, Principal, User | None] | None:
    """Look up a valid session from the request cookie."""
    cookie_name = session_settings.cookie_name
    raw_token: str | None = request.cookies.get(cookie_name)
    if not raw_token:
        return None

    token_hash = hash_token(raw_token)
    session = (
        db.query(AuthSession).filter(
            AuthSession.token_hash == token_hash,
            AuthSession.revoked_at.is_(None),
        ).first()
    )
    if session is None:
        return None

    now = datetime.now(UTC)
    if session.expires_at.tzinfo is None:
        expires = session.expires_at.replace(tzinfo=UTC)
    else:
        expires = session.expires_at
    if now > expires:
        return None

    principal = db.query(Principal).filter(Principal.id == session.principal_id).first()
    if principal is None or principal.revoked_at is not None:
        return None

    user: User | None = None
    if principal.user_id:
        user = db.query(User).filter(User.id == principal.user_id).first()

    # Sliding expiry: update last_seen_at if > 60s; renew remembered sessions past threshold
    needs_commit = False
    if session.last_seen_at.tzinfo is None:
        last_seen = session.last_seen_at.replace(tzinfo=UTC)
    else:
        last_seen = session.last_seen_at
    if (now - last_seen).total_seconds() > 60:
        session.last_seen_at = now
        needs_commit = True

    if session.remembered:
        ttl = timedelta(days=session_settings.session_ttl_days)
        remaining = expires - now
        threshold = ttl * session_settings.renew_threshold_fraction
        if remaining < threshold:
            session.expires_at = now + ttl
            needs_commit = True

    if needs_commit:
        db.commit()

    return session, principal, user


_db_dep = Depends(get_db)


def get_optional_principal(
    request: Request,
    db: Session = _db_dep,
) -> CurrentPrincipal | None:
    """Return the current principal if a valid session exists, else None."""
    result = _resolve_session(request, db)
    if result is None:
        return None
    session, principal, user = result
    email_verified = False
    if user and user.email_verified_at is not None:
        email_verified = True
    mode = "authenticated" if principal.user_id else "guest"
    return CurrentPrincipal(
        principal_id=principal.id,
        user_id=principal.user_id,
        mode=mode,
        email_verified=email_verified,
        session_id=session.id,
    )


_opt_principal_dep = Depends(get_optional_principal)


def get_current_principal(
    principal: CurrentPrincipal | None = _opt_principal_dep,
) -> CurrentPrincipal:
    """Require any valid session (guest or authenticated)."""
    if principal is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "auth.session_required", "message": "未登录"},
        )
    return principal


_current_principal_dep = Depends(get_current_principal)


def require_user(
    principal: CurrentPrincipal = _current_principal_dep,
) -> CurrentPrincipal:
    """Require an authenticated (non-guest) session."""
    if principal.mode != "authenticated":
        raise HTTPException(
            status_code=401,
            detail={"code": "auth.login_required", "message": "此操作需要登录"},
        )
    return principal


def get_owned_principal_ids(
    principal: CurrentPrincipal = _current_principal_dep,
    db: Session = _db_dep,
) -> list[str]:
    """Return all principal IDs owned by the current principal/user."""
    if not principal.user_id:
        return [principal.principal_id]
    rows = (
        db.query(Principal.id)
        .filter(
            Principal.user_id == principal.user_id,
            Principal.revoked_at.is_(None),
        )
        .all()
    )
    ids = {r[0] for r in rows}
    ids.add(principal.principal_id)
    return list(ids)


_require_user_dep = Depends(require_user)


def require_owned_principal_ids(
    principal: CurrentPrincipal = _require_user_dep,
    db: Session = _db_dep,
) -> list[str]:
    """Require an authenticated user and return their owned principal IDs."""
    return get_owned_principal_ids(principal, db)


def verify_csrf(
    request: Request,
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    db: Session = _db_dep,
) -> None:
    """CSRF triple-check dependency for unsafe methods on auth/user endpoints.

    Checks:
    1. X-CSRF-Token header matches session's plaintext csrf_token (constant-time compare).
    2. Origin (if present) must be in allowed origins.
    3. Sec-Fetch-Site (if present) must be same-origin, same-site, or none.
    """
    # --- 1. Token check ---
    if not x_csrf_token:
        raise HTTPException(
            status_code=403,
            detail={"code": "auth.csrf_failed", "message": "CSRF 校验失败"},
        )

    result = _resolve_session(request, db)
    if result is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "auth.session_required", "message": "未登录"},
        )
    session, _, _ = result

    if not secrets.compare_digest(x_csrf_token, session.csrf_token):
        raise HTTPException(
            status_code=403,
            detail={"code": "auth.csrf_failed", "message": "CSRF Token 不匹配"},
        )

    # --- 2. Origin check ---
    origin = request.headers.get("origin")
    if origin:
        origin_clean = origin.rstrip("/")
        proto = request.headers.get("x-forwarded-proto") or request.url.scheme
        forwarded_host = request.headers.get("x-forwarded-host")
        host = forwarded_host or request.headers.get("host") or request.url.netloc
        self_origin = f"{proto}://{host}".rstrip("/")
        if origin_clean != self_origin and origin_clean not in session_settings.cors_origins:
            raise HTTPException(
                status_code=403,
                detail={"code": "auth.csrf_failed", "message": "Origin 不在允许列表"},
            )

    # --- 3. Sec-Fetch-Site check ---
    sec_fetch_site = request.headers.get("sec-fetch-site")
    if sec_fetch_site and sec_fetch_site not in ("same-origin", "same-site", "none"):
        raise HTTPException(
            status_code=403,
            detail={"code": "auth.csrf_failed", "message": "Sec-Fetch-Site 不允许"},
        )

