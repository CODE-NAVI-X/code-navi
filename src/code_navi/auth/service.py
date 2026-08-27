"""Auth service: session management, registration, login, logout, tokens."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import Request, Response
from sqlalchemy.orm import Session

from .email_sender import EmailSender
from .models import AuthEvent, AuthOneTimeToken, AuthSession, PasswordCredential, Principal, User
from .security import (
    generate_csrf_token,
    generate_one_time_token,
    generate_session_token,
    hash_password,
    hash_token,
    normalize_email,
    validate_email_format,
    validate_password_strength,
    verify_password,
)
from .settings import session_settings

logger = logging.getLogger(__name__)


# ── Errors ───────────────────────────────────────────────────────────────


class AuthError(Exception):
    """Raised by service methods; routers convert to HTTPException."""

    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


# ── Cookie helpers ─────────────────────────────────────────────────────


def _set_session_cookie(response: Response, token: str, remembered: bool) -> None:
    """Write the session cookie onto the response."""
    settings = session_settings
    kwargs: dict = {
        "key": settings.cookie_name,
        "value": token,
        "httponly": True,
        "samesite": settings.cookie_samesite,
        "secure": settings.cookie_secure,
        "path": "/",
    }
    if settings.cookie_secure:
        # __Host- prefix requires no Domain attribute
        pass
    if remembered:
        kwargs["max_age"] = settings.session_ttl_days * 86400
    response.set_cookie(**kwargs)


def _clear_session_cookie(response: Response) -> None:
    """Expire the session cookie."""
    settings = session_settings
    response.delete_cookie(
        key=settings.cookie_name,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite=settings.cookie_samesite,
    )


# ── Session creation ─────────────────────────────────────────────────────


def _create_session(
    db: Session,
    principal: Principal,
    request: Request,
    *,
    remembered: bool = False,
) -> tuple[str, str, AuthSession]:
    """Create a new auth session, returning (raw_token, raw_csrf, session_record)."""
    now = datetime.now(UTC)
    raw_token = generate_session_token()
    raw_csrf = generate_csrf_token()
    ttl = (
        timedelta(days=session_settings.session_ttl_days)
        if remembered
        else timedelta(seconds=session_settings.session_ttl_seconds)
    )
    ua = request.headers.get("user-agent", "")[:200] or None
    session = AuthSession(
        id=str(uuid4()),
        principal_id=principal.id,
        token_hash=hash_token(raw_token),
        csrf_token=raw_csrf,
        remembered=remembered,
        created_at=now,
        last_seen_at=now,
        expires_at=now + ttl,
        user_agent_label=ua,
    )
    db.add(session)
    db.flush()
    return raw_token, raw_csrf, session


def _resolve_session_from_request(
    db: Session, request: Request
) -> tuple[AuthSession, Principal] | None:
    """Return (session, principal) for a valid cookie session, else None."""
    cookie_name = session_settings.cookie_name
    raw_token = request.cookies.get(cookie_name)
    if not raw_token:
        return None
    token_hash = hash_token(raw_token)
    now = datetime.now(UTC)
    session = (
        db.query(AuthSession)
        .filter(
            AuthSession.token_hash == token_hash,
            AuthSession.revoked_at.is_(None),
        )
        .first()
    )
    if not session:
        return None
    exp = session.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=UTC)
    if now > exp:
        return None
    principal = db.query(Principal).filter(Principal.id == session.principal_id).first()
    if not principal or principal.revoked_at is not None:
        return None
    return session, principal


# ── Guest sessions ─────────────────────────────────────────────────────────


def get_or_create_guest_session(
    db: Session,
    request: Request,
    response: Response,
) -> tuple[AuthSession, Principal, str]:
    """Idempotent: returns existing session or creates a new Guest one with stable csrf."""
    existing = _resolve_session_from_request(db, request)
    if existing:
        session, principal = existing
        return session, principal, session.csrf_token

    # Create guest principal + session
    now = datetime.now(UTC)
    principal = Principal(
        id=str(uuid4()),
        user_id=None,
        origin="guest",
        created_at=now,
    )
    db.add(principal)
    db.flush()

    raw_token, raw_csrf, session = _create_session(db, principal, request, remembered=False)
    db.commit()

    _set_session_cookie(response, raw_token, remembered=False)
    return session, principal, raw_csrf


# ── Registration ───────────────────────────────────────────────────────────


def register_user(
    db: Session,
    request: Request,
    response: Response,
    *,
    email: str,
    password: str,
    display_name: str,
    claim_guest_data: bool,
) -> tuple[AuthSession, Principal, User, str, dict | None]:
    """Register a new user, create Principal and session, return claim result."""
    email_norm = normalize_email(email)
    if not validate_email_format(email):
        raise AuthError("auth.validation_failed", "邮箱格式不正确", 422)

    err = validate_password_strength(password, email)
    if err:
        raise AuthError("auth.password_too_weak", err, 422)

    display_name = display_name.strip()
    if not display_name or len(display_name) > 100:
        raise AuthError("auth.validation_failed", "显示名必填且不超过 100 字符", 422)

    existing = db.query(User).filter(User.email_normalized == email_norm).first()
    if existing:
        raise AuthError("auth.email_taken", "该邮箱已被注册", 409)

    # Determine initial status
    status = "pending_verification" if session_settings.require_email_verification else "active"
    now = datetime.now(UTC)

    user = User(
        id=str(uuid4()),
        email_normalized=email_norm,
        email_display=email.strip(),
        display_name=display_name,
        status=status,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.flush()

    cred = PasswordCredential(
        id=str(uuid4()),
        user_id=user.id,
        password_hash=hash_password(password),
        created_at=now,
        updated_at=now,
    )
    db.add(cred)

    # Handle guest data claim
    claim_result = None
    existing_session = _resolve_session_from_request(db, request)
    principal: Principal

    if claim_guest_data and existing_session:
        old_session, guest_principal = existing_session
        if guest_principal.user_id is None:  # still a guest
            guest_principal.user_id = user.id
            guest_principal.claimed_at = now
            principal = guest_principal
            claim_result = _count_guest_data(db, guest_principal.id)
        else:
            principal = _new_account_principal(db, user.id, now)
    else:
        principal = _new_account_principal(db, user.id, now)

    db.flush()

    # Revoke any existing session
    if existing_session:
        existing_session[0].revoked_at = now

    raw_token, raw_csrf, session = _create_session(db, principal, request, remembered=False)

    _log_event(
        db,
        event_type="register",
        user_id=user.id,
        principal_id=principal.id,
        request=request,
    )
    db.commit()

    _set_session_cookie(response, raw_token, remembered=False)
    return session, principal, user, raw_csrf, claim_result


def _new_account_principal(db: Session, user_id: str, now: datetime) -> Principal:
    p = Principal(
        id=str(uuid4()),
        user_id=user_id,
        origin="account",
        created_at=now,
    )
    db.add(p)
    return p


def _count_guest_data(db: Session, principal_id: str) -> dict:
    """Count guest-owned records for claim result."""
    from ..workspaces.models import TaskModel, WorkspaceActivityModel, WorkspaceModel

    workspace_count = (
        db.query(WorkspaceModel)
        .filter(WorkspaceModel.owner_principal_id == principal_id)
        .count()
    )
    task_count = (
        db.query(TaskModel)
        .join(WorkspaceModel, TaskModel.workspace_id == WorkspaceModel.id)
        .filter(WorkspaceModel.owner_principal_id == principal_id)
        .count()
    )
    activity_count = (
        db.query(WorkspaceActivityModel)
        .join(WorkspaceModel, WorkspaceActivityModel.workspace_id == WorkspaceModel.id)
        .filter(WorkspaceModel.owner_principal_id == principal_id)
        .count()
    )
    return {
        "claimed": True,
        "workspaceCount": workspace_count,
        "taskCount": task_count,
        "activityCount": activity_count,
    }


# ── Login ───────────────────────────────────────────────────────────────────


def login_user(
    db: Session,
    request: Request,
    response: Response,
    *,
    email: str,
    password: str,
    remember_me: bool,
    claim_guest_data: bool,
) -> tuple[AuthSession, Principal, User, str, dict | None]:
    """Authenticate credentials, create new session, return claim result."""
    email_norm = normalize_email(email)
    user = db.query(User).filter(User.email_normalized == email_norm).first()

    # Constant-time path: always run verify_password to prevent timing attacks
    dummy_hash = (
        "$argon2id$v=19$m=65536,t=3,p=4$dummydummydummy$dummydummydummydummydummydummydummy"
    )
    cred: PasswordCredential | None = None
    if user:
        cred = (
            db.query(PasswordCredential)
            .filter(PasswordCredential.user_id == user.id)
            .first()
        )

    hash_to_check = cred.password_hash if cred else dummy_hash
    valid = verify_password(password, hash_to_check)

    if not user or not cred or not valid:
        _log_event(db, event_type="login_failed", request=request)
        db.commit()
        raise AuthError("auth.invalid_credentials", "邮箱或密码错误", 401)

    if user.status == "disabled":
        raise AuthError("auth.account_disabled", "账户已被禁用", 403)
    if user.status == "pending_deletion":
        raise AuthError("auth.account_pending_deletion", "账户处于待删除状态", 403)

    now = datetime.now(UTC)
    claim_result = None
    existing_session = _resolve_session_from_request(db, request)
    principal: Principal

    if claim_guest_data and existing_session:
        old_session, guest_principal = existing_session
        if guest_principal.user_id is None:
            guest_principal.user_id = user.id
            guest_principal.claimed_at = now
            principal = guest_principal
            claim_result = _count_guest_data(db, guest_principal.id)
        else:
            principal = _new_account_principal(db, user.id, now)
    else:
        if existing_session and existing_session[1].user_id is None:
            # Guest session exists but not claiming - orphan it, create account principal
            claim_result = {"claimed": False}
        principal = _new_account_principal(db, user.id, now)

    db.flush()

    # Revoke old session
    if existing_session:
        existing_session[0].revoked_at = now

    raw_token, raw_csrf, session = _create_session(
        db, principal, request, remembered=remember_me
    )

    _log_event(
        db,
        event_type="login_success",
        user_id=user.id,
        principal_id=principal.id,
        request=request,
    )
    db.commit()

    _set_session_cookie(response, raw_token, remembered=remember_me)
    return session, principal, user, raw_csrf, claim_result


# ── Logout ──────────────────────────────────────────────────────────────────


def logout(
    db: Session,
    request: Request,
    response: Response,
) -> None:
    """Revoke the current session and clear the cookie."""
    existing = _resolve_session_from_request(db, request)
    if existing:
        session, principal = existing
        session.revoked_at = datetime.now(UTC)
        _log_event(
            db,
            event_type="logout",
            user_id=principal.user_id,
            principal_id=principal.id,
            request=request,
        )
        db.commit()
    _clear_session_cookie(response)


def logout_all(
    db: Session,
    request: Request,
    response: Response,
    *,
    user_id: str,
    current_password: str,
) -> None:
    """Verify password then revoke all sessions for the user."""
    cred = db.query(PasswordCredential).filter(PasswordCredential.user_id == user_id).first()
    if not cred or not verify_password(current_password, cred.password_hash):
        raise AuthError("auth.password_incorrect", "当前密码不正确", 401)

    now = datetime.now(UTC)
    principals = db.query(Principal).filter(Principal.user_id == user_id).all()
    for p in principals:
        for s in db.query(AuthSession).filter(
            AuthSession.principal_id == p.id,
            AuthSession.revoked_at.is_(None),
        ).all():
            s.revoked_at = now

    _log_event(db, event_type="logout_all", user_id=user_id, request=request)
    db.commit()
    _clear_session_cookie(response)


# ── Session listing and revocation ────────────────────────────────────────────


def list_user_sessions(
    db: Session,
    user_id: str,
    current_session_id: str,
) -> list[dict]:
    """Return active sessions for a user."""
    principals = db.query(Principal).filter(Principal.user_id == user_id).all()
    p_ids = [p.id for p in principals]
    now = datetime.now(UTC)
    sessions = (
        db.query(AuthSession)
        .filter(
            AuthSession.principal_id.in_(p_ids),
            AuthSession.revoked_at.is_(None),
        )
        .order_by(AuthSession.created_at.desc())
        .all()
    )
    result = []
    for s in sessions:
        exp = s.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=UTC)
        if now > exp:
            continue
        result.append({
            "id": s.id,
            "createdAt": s.created_at.replace(tzinfo=UTC).isoformat(),
            "lastSeenAt": s.last_seen_at.replace(tzinfo=UTC).isoformat(),
            "expiresAt": exp.isoformat(),
            "userAgentLabel": s.user_agent_label,
            "current": s.id == current_session_id,
        })
    return result


def revoke_session(
    db: Session,
    request: Request,
    response: Response,
    *,
    session_id: str,
    user_id: str,
    current_session_id: str,
) -> None:
    """Revoke a specific session belonging to this user."""
    principals = db.query(Principal).filter(Principal.user_id == user_id).all()
    p_ids = [p.id for p in principals]
    target = (
        db.query(AuthSession)
        .filter(
            AuthSession.id == session_id,
            AuthSession.principal_id.in_(p_ids),
        )
        .first()
    )
    if not target:
        raise AuthError("auth.session_not_found", "会话不存在", 404)

    target.revoked_at = datetime.now(UTC)
    _log_event(db, event_type="session_revoked", user_id=user_id, request=request)
    db.commit()

    # If revoking current session, clear the cookie too
    if session_id == current_session_id:
        _clear_session_cookie(response)


# ── Password management ─────────────────────────────────────────────────────


def request_password_reset(
    db: Session,
    email: str,
    email_sender: EmailSender,
) -> None:
    """Send password reset email if account exists (anti-enum: always silent)."""
    email_norm = normalize_email(email)
    user = db.query(User).filter(User.email_normalized == email_norm).first()
    if not user or user.status in ("disabled",):
        return  # anti-enumeration: no error

    raw_token = generate_one_time_token()
    now = datetime.now(UTC)
    token_record = AuthOneTimeToken(
        id=str(uuid4()),
        user_id=user.id,
        purpose="password_reset",
        token_hash=hash_token(raw_token),
        created_at=now,
        expires_at=now
        + timedelta(minutes=session_settings.reset_token_ttl_minutes),
    )
    db.add(token_record)
    _log_event(db, event_type="password_reset_requested", user_id=user.id)
    db.commit()
    email_sender.send_password_reset_email(user.email_display, raw_token)


def reset_password(
    db: Session,
    request: Request,
    response: Response,
    *,
    token: str,
    new_password: str,
) -> None:
    """Consume reset token, update password, revoke all sessions."""
    token_hash = hash_token(token)
    now = datetime.now(UTC)
    record = (
        db.query(AuthOneTimeToken)
        .filter(
            AuthOneTimeToken.token_hash == token_hash,
            AuthOneTimeToken.purpose == "password_reset",
            AuthOneTimeToken.consumed_at.is_(None),
        )
        .first()
    )
    if not record:
        raise AuthError("auth.invalid_or_expired_token", "重置链接无效或已过期", 400)
    exp = record.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=UTC)
    if now > exp:
        raise AuthError("auth.invalid_or_expired_token", "重置链接已过期", 400)

    err = validate_password_strength(new_password)
    if err:
        raise AuthError("auth.password_too_weak", err, 422)

    user_id = record.user_id
    cred = db.query(PasswordCredential).filter(PasswordCredential.user_id == user_id).first()
    if not cred:
        raise AuthError("auth.invalid_or_expired_token", "账户不存在", 400)

    cred.password_hash = hash_password(new_password)
    cred.updated_at = now
    record.consumed_at = now

    # Revoke all sessions for this user
    principals = db.query(Principal).filter(Principal.user_id == user_id).all()
    for p in principals:
        for s in db.query(AuthSession).filter(
            AuthSession.principal_id == p.id,
            AuthSession.revoked_at.is_(None),
        ).all():
            s.revoked_at = now

    _log_event(db, event_type="password_reset", user_id=user_id, request=request)
    db.commit()
    _clear_session_cookie(response)


def change_password(
    db: Session,
    request: Request,
    *,
    user_id: str,
    current_session_id: str,
    current_password: str,
    new_password: str,
) -> None:
    """Change password, keep current session, revoke others."""
    cred = db.query(PasswordCredential).filter(PasswordCredential.user_id == user_id).first()
    if not cred or not verify_password(current_password, cred.password_hash):
        raise AuthError("auth.password_incorrect", "当前密码不正确", 401)

    err = validate_password_strength(new_password)
    if err:
        raise AuthError("auth.password_too_weak", err, 422)

    now = datetime.now(UTC)
    cred.password_hash = hash_password(new_password)
    cred.updated_at = now

    # Revoke other sessions
    principals = db.query(Principal).filter(Principal.user_id == user_id).all()
    for p in principals:
        for s in db.query(AuthSession).filter(
            AuthSession.principal_id == p.id,
            AuthSession.revoked_at.is_(None),
            AuthSession.id != current_session_id,
        ).all():
            s.revoked_at = now

    _log_event(db, event_type="password_changed", user_id=user_id, request=request)
    db.commit()


# ── Email verification ─────────────────────────────────────────────────────


def request_email_verification(
    db: Session,
    email_sender: EmailSender,
    *,
    user_id: str | None = None,
    email: str | None = None,
) -> None:
    """Send email verification. Anti-enum: always silent."""
    user: User | None = None
    if user_id:
        user = db.query(User).filter(User.id == user_id).first()
    elif email:
        email_norm = normalize_email(email)
        user = (
            db.query(User)
            .filter(
                User.email_normalized == email_norm,
                User.status == "pending_verification",
            )
            .first()
        )

    if not user:
        return
    if user.email_verified_at is not None:
        return

    raw_token = generate_one_time_token()
    now = datetime.now(UTC)
    record = AuthOneTimeToken(
        id=str(uuid4()),
        user_id=user.id,
        purpose="email_verification",
        token_hash=hash_token(raw_token),
        created_at=now,
        expires_at=now + timedelta(minutes=session_settings.reset_token_ttl_minutes),
    )
    db.add(record)
    _log_event(db, event_type="email_verification_sent", user_id=user.id)
    db.commit()
    email_sender.send_verification_email(user.email_display, raw_token)


def confirm_email_verification(
    db: Session,
    request: Request,
    response: Response,
    token: str,
) -> None:
    """Mark email as verified and upgrade user status if pending."""
    token_hash = hash_token(token)
    now = datetime.now(UTC)
    record = (
        db.query(AuthOneTimeToken)
        .filter(
            AuthOneTimeToken.token_hash == token_hash,
            AuthOneTimeToken.purpose == "email_verification",
            AuthOneTimeToken.consumed_at.is_(None),
        )
        .first()
    )
    if not record:
        raise AuthError("auth.invalid_or_expired_token", "Token 无效或已过期", 400)
    exp = record.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=UTC)
    if now > exp:
        raise AuthError("auth.invalid_or_expired_token", "Token 已过期", 400)

    user = db.query(User).filter(User.id == record.user_id).first()
    if not user:
        raise AuthError("auth.invalid_or_expired_token", "账户不存在", 400)
    if user.email_verified_at is not None:
        raise AuthError("auth.email_already_verified", "邮箱已经验证", 400)

    user.email_verified_at = now
    if user.status == "pending_verification":
        user.status = "active"
    record.consumed_at = now

    existing_session = _resolve_session_from_request(db, request)
    if existing_session:
        old_session, principal = existing_session
        old_session.revoked_at = now
        raw_token, raw_csrf, new_session = _create_session(
            db, principal, request, remembered=old_session.remembered
        )
        _set_session_cookie(response, raw_token, remembered=old_session.remembered)

    _log_event(db, event_type="email_verified", user_id=user.id, request=request)
    db.commit()


# ── Email change ────────────────────────────────────────────────────────────


def request_email_change(
    db: Session,
    email_sender: EmailSender,
    *,
    user_id: str,
    new_email: str,
    current_password: str,
) -> None:
    """Initiate email change: verify password, check availability, send token."""
    cred = db.query(PasswordCredential).filter(PasswordCredential.user_id == user_id).first()
    if not cred or not verify_password(current_password, cred.password_hash):
        raise AuthError("auth.password_incorrect", "当前密码不正确", 401)

    new_email_norm = normalize_email(new_email)
    if not validate_email_format(new_email):
        raise AuthError("auth.validation_failed", "邮箱格式不正确", 422)

    taken = db.query(User).filter(User.email_normalized == new_email_norm).first()
    if taken:
        raise AuthError("auth.email_in_use", "该邮箱已被使用", 409)

    raw_token = generate_one_time_token()
    now = datetime.now(UTC)
    record = AuthOneTimeToken(
        id=str(uuid4()),
        user_id=user_id,
        purpose="email_change",
        token_hash=hash_token(raw_token),
        new_email_normalized=new_email_norm,
        created_at=now,
        expires_at=now + timedelta(minutes=session_settings.reset_token_ttl_minutes),
    )
    db.add(record)
    db.commit()
    email_sender.send_email_change_email(new_email.strip(), raw_token)


def confirm_email_change(
    db: Session,
    request: Request,
    response: Response,
    *,
    user_id: str,
    current_session_id: str,
    token: str,
) -> None:
    """Apply email change, revoke other sessions and rotate current session."""
    token_hash = hash_token(token)
    now = datetime.now(UTC)
    record = (
        db.query(AuthOneTimeToken)
        .filter(
            AuthOneTimeToken.token_hash == token_hash,
            AuthOneTimeToken.purpose == "email_change",
            AuthOneTimeToken.user_id == user_id,
            AuthOneTimeToken.consumed_at.is_(None),
        )
        .first()
    )
    if not record:
        raise AuthError("auth.invalid_or_expired_token", "Token 无效或已过期", 400)
    exp = record.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=UTC)
    if now > exp:
        raise AuthError("auth.invalid_or_expired_token", "Token 已过期", 400)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise AuthError("auth.invalid_or_expired_token", "账户不存在", 400)

    user.email_normalized = record.new_email_normalized  # type: ignore[assignment]
    user.email_display = record.new_email_normalized  # type: ignore[assignment]
    user.email_verified_at = now
    user.updated_at = now
    record.consumed_at = now

    existing_session = _resolve_session_from_request(db, request)
    remembered = existing_session[0].remembered if existing_session else False

    # Revoke all sessions
    principals = db.query(Principal).filter(Principal.user_id == user_id).all()
    for p in principals:
        for s in db.query(AuthSession).filter(
            AuthSession.principal_id == p.id,
            AuthSession.revoked_at.is_(None),
        ).all():
            s.revoked_at = now

    # Rotate session: create new active session on this principal
    target_principal = (
        existing_session[1]
        if existing_session
        else (principals[0] if principals else None)
    )
    if target_principal:
        raw_token, raw_csrf, new_session = _create_session(
            db, target_principal, request, remembered=remembered
        )
        _set_session_cookie(response, raw_token, remembered=remembered)

    _log_event(db, event_type="email_change_confirmed", user_id=user_id, request=request)
    db.commit()


# ── User management ──────────────────────────────────────────────────────────


def update_display_name(db: Session, user_id: str, display_name: str) -> User:
    """Update only display_name (1-100 chars)."""
    display_name = display_name.strip()
    if not display_name or len(display_name) > 100:
        raise AuthError("auth.validation_failed", "显示名必填且不超过 100 字符", 422)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise AuthError("auth.validation_failed", "用户不存在", 404)
    user.display_name = display_name
    user.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(user)
    return user


def request_account_deletion(
    db: Session,
    request: Request,
    response: Response,
    *,
    user_id: str,
    current_password: str,
    confirmation: str,
) -> None:
    """Initiate account deletion (pending_deletion state)."""
    if confirmation != "DELETE":
        raise AuthError("auth.validation_failed", '请输入确认文本 "DELETE"', 422)

    cred = db.query(PasswordCredential).filter(PasswordCredential.user_id == user_id).first()
    if not cred or not verify_password(current_password, cred.password_hash):
        raise AuthError("auth.password_incorrect", "当前密码不正确", 401)

    now = datetime.now(UTC)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise AuthError("auth.validation_failed", "用户不存在", 404)

    user.status = "pending_deletion"
    user.deletion_requested_at = now
    user.updated_at = now

    # Revoke all sessions
    principals = db.query(Principal).filter(Principal.user_id == user_id).all()
    for p in principals:
        for s in db.query(AuthSession).filter(
            AuthSession.principal_id == p.id,
            AuthSession.revoked_at.is_(None),
        ).all():
            s.revoked_at = now

    _log_event(db, event_type="deletion_requested", user_id=user_id, request=request)
    db.commit()
    _clear_session_cookie(response)


def cancel_account_deletion(
    db: Session,
    user_id: str,
) -> None:
    """Cancel pending deletion - restore to active."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise AuthError("auth.validation_failed", "用户不存在", 404)
    if user.status != "pending_deletion":
        raise AuthError("auth.validation_failed", "账户未处于待删除状态", 400)
    user.status = "active"
    user.deletion_requested_at = None
    user.updated_at = datetime.now(UTC)
    _log_event(db, event_type="deletion_cancelled", user_id=user_id)
    db.commit()


# ── Audit logging ─────────────────────────────────────────────────────────────


def _log_event(
    db: Session,
    *,
    event_type: str,
    user_id: str | None = None,
    principal_id: str | None = None,
    request: Request | None = None,
    metadata: dict | None = None,
) -> None:
    ip: str | None = None
    if request:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
        elif request.client:
            ip = request.client.host
    ua = request.headers.get("user-agent") if request else None
    event = AuthEvent(
        id=str(uuid4()),
        event_type=event_type,
        user_id=user_id,
        principal_id=principal_id,
        ip_address=ip,
        user_agent=ua[:512] if ua else None,
        metadata_=metadata,
    )
    db.add(event)
