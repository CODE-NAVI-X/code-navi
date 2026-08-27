"""Auth API router: all /api/v1/auth/* and /api/v1/users/me/* endpoints."""

from __future__ import annotations

import logging
from datetime import UTC

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from ..db import get_db
from .dependencies import CurrentPrincipal, get_optional_principal, require_user, verify_csrf
from .email_sender import EmailSender, get_email_sender
from .models import AuthSession, Principal, User
from .rate_limiter import InProcessRateLimiter, get_rate_limiter
from .schemas import (
    ChangePasswordRequest,
    ClaimResult,
    DeleteAccountRequest,
    EmailChangeConfirmRequest,
    EmailChangeRequest,
    EmailVerificationConfirmRequest,
    EmailVerificationRequest,
    ForgotPasswordRequest,
    LoginRequest,
    LogoutAllRequest,
    RegisterRequest,
    ResetPasswordRequest,
    SessionInfo,
    SessionItem,
    SessionListResponse,
    SessionResponse,
    UpdateProfileRequest,
    UserOut,
    UserResponse,
)
from .service import (
    AuthError,
    cancel_account_deletion,
    change_password,
    confirm_email_change,
    confirm_email_verification,
    get_or_create_guest_session,
    list_user_sessions,
    login_user,
    logout,
    logout_all,
    register_user,
    request_account_deletion,
    request_email_change,
    request_email_verification,
    request_password_reset,
    reset_password,
    revoke_session,
    update_display_name,
)
from .settings import session_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Auth"])

_db_dep = Depends(get_db)
_limiter_dep = Depends(get_rate_limiter)
_email_sender_dep = Depends(get_email_sender)
_opt_principal_dep = Depends(get_optional_principal)
_require_user_dep = Depends(require_user)
_verify_csrf_dep = Depends(verify_csrf)


def _auth_error_to_http(exc: AuthError) -> HTTPException:
    return HTTPException(
        status_code=exc.status,
        detail={"code": exc.code, "message": exc.message, "fieldErrors": {}},
    )


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _rate_limit(
    limiter: InProcessRateLimiter, request: Request, identifier: str
) -> None:
    ip = _get_client_ip(request)
    if not limiter.check(ip, identifier):
        raise HTTPException(
            status_code=429,
            detail={
                "code": "auth.rate_limited",
                "message": "请求过于频繁，请稍候再试",
                "fieldErrors": {},
            },
        )


def _build_session_response(
    session: AuthSession,
    principal: Principal,
    user: User | None,
    raw_csrf: str,
    claim_result: dict | None,
) -> SessionResponse:
    exp = session.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=UTC)
    created = session.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)

    mode = "authenticated" if principal.user_id else "guest"
    user_out = None
    if user:
        user_out = UserOut(
            id=user.id,
            displayName=user.display_name,
            email=user.email_display,
            emailVerified=user.email_verified_at is not None,
            status=user.status,
        )

    return SessionResponse(
        mode=mode,
        user=user_out,
        session=SessionInfo(
            id=session.id,
            createdAt=created.isoformat(),
            expiresAt=exp.isoformat(),
            remembered=session.remembered,
        ),
        csrfToken=raw_csrf,
        claimResult=ClaimResult(**claim_result) if claim_result else None,
    )


# ============================================================
# Auth routes
# ============================================================


@router.post("/api/v1/auth/guest-sessions", response_model=SessionResponse)
def create_guest_session(
    request: Request,
    response: Response,
    db: Session = _db_dep,
) -> SessionResponse:
    """Idempotent: return existing session or create a new guest one."""
    session, principal, raw_csrf = get_or_create_guest_session(db, request, response)
    user: User | None = None
    if principal.user_id:
        user = db.query(User).filter(User.id == principal.user_id).first()
    return _build_session_response(session, principal, user, raw_csrf, None)


@router.get("/api/v1/auth/session", response_model=SessionResponse)
def get_session(
    request: Request,
    response: Response,
    db: Session = _db_dep,
) -> SessionResponse:
    """Return current session state; creates a guest session if none exists."""
    return create_guest_session(request, response, db)


@router.post("/api/v1/auth/register", response_model=SessionResponse, status_code=201)
def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    db: Session = _db_dep,
    limiter: InProcessRateLimiter = _limiter_dep,
) -> SessionResponse:
    if not session_settings.allow_registration:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "auth.registration_disabled",
                "message": "系统当前已关闭新用户注册",
                "fieldErrors": {},
            },
        )
    _rate_limit(limiter, request, body.email)
    try:
        session, principal, user, raw_csrf, claim_result = register_user(
            db,
            request,
            response,
            email=body.email,
            password=body.password,
            display_name=body.displayName,
            claim_guest_data=body.claimGuestData,
        )
    except AuthError as exc:
        raise _auth_error_to_http(exc) from exc

    return _build_session_response(session, principal, user, raw_csrf, claim_result)


@router.post("/api/v1/auth/login", response_model=SessionResponse)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: Session = _db_dep,
    limiter: InProcessRateLimiter = _limiter_dep,
) -> SessionResponse:
    _rate_limit(limiter, request, body.email)
    try:
        session, principal, user, raw_csrf, claim_result = login_user(
            db,
            request,
            response,
            email=body.email,
            password=body.password,
            remember_me=body.rememberMe,
            claim_guest_data=body.claimGuestData,
        )
    except AuthError as exc:
        raise _auth_error_to_http(exc) from exc

    return _build_session_response(session, principal, user, raw_csrf, claim_result)


@router.post("/api/v1/auth/logout", status_code=204)
def logout_endpoint(
    request: Request,
    response: Response,
    db: Session = _db_dep,
    _csrf: None = _verify_csrf_dep,
) -> None:
    logout(db, request, response)


@router.post("/api/v1/auth/logout-all", status_code=204)
def logout_all_endpoint(
    body: LogoutAllRequest,
    request: Request,
    response: Response,
    principal: CurrentPrincipal = _require_user_dep,
    db: Session = _db_dep,
    _csrf: None = _verify_csrf_dep,
) -> None:
    try:
        logout_all(
            db,
            request,
            response,
            user_id=principal.user_id,  # type: ignore[arg-type]
            current_password=body.currentPassword,
        )
    except AuthError as exc:
        raise _auth_error_to_http(exc) from exc


@router.get("/api/v1/auth/sessions", response_model=SessionListResponse)
def list_sessions(
    principal: CurrentPrincipal = _require_user_dep,
    db: Session = _db_dep,
) -> SessionListResponse:
    items = list_user_sessions(
        db,
        user_id=principal.user_id,  # type: ignore[arg-type]
        current_session_id=principal.session_id,
    )
    return SessionListResponse(items=[SessionItem(**i) for i in items])


@router.delete("/api/v1/auth/sessions/{session_id}", status_code=204)
def revoke_session_endpoint(
    session_id: str,
    request: Request,
    response: Response,
    principal: CurrentPrincipal = _require_user_dep,
    db: Session = _db_dep,
    _csrf: None = _verify_csrf_dep,
) -> None:
    try:
        revoke_session(
            db,
            request,
            response,
            session_id=session_id,
            user_id=principal.user_id,  # type: ignore[arg-type]
            current_session_id=principal.session_id,
        )
    except AuthError as exc:
        raise _auth_error_to_http(exc) from exc


@router.post("/api/v1/auth/email-verification/request", status_code=202)
def request_email_verification_endpoint(
    body: EmailVerificationRequest,
    request: Request,
    principal: CurrentPrincipal | None = _opt_principal_dep,
    db: Session = _db_dep,
    email_sender: EmailSender = _email_sender_dep,
    limiter: InProcessRateLimiter = _limiter_dep,
) -> dict:
    if not principal and not body.email:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "auth.session_required",
                "message": "未登录",
                "fieldErrors": {},
            },
        )
    identifier = body.email or (principal.user_id if principal else "unknown")
    _rate_limit(limiter, request, identifier or "unknown")
    user_id = principal.user_id if principal and principal.mode == "authenticated" else None
    request_email_verification(
        db,
        email_sender,
        user_id=user_id,
        email=body.email,
    )
    return {}


@router.post("/api/v1/auth/email-verification/confirm", status_code=204)
def confirm_email_verification_endpoint(
    body: EmailVerificationConfirmRequest,
    request: Request,
    response: Response,
    db: Session = _db_dep,
) -> None:
    try:
        confirm_email_verification(db, request, response, body.token)
    except AuthError as exc:
        raise _auth_error_to_http(exc) from exc


@router.post("/api/v1/auth/password/forgot", status_code=202)
def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    db: Session = _db_dep,
    email_sender: EmailSender = _email_sender_dep,
    limiter: InProcessRateLimiter = _limiter_dep,
) -> dict:
    _rate_limit(limiter, request, body.email)
    request_password_reset(db, body.email, email_sender)
    return {}


@router.post("/api/v1/auth/password/reset", status_code=204)
def reset_password_endpoint(
    body: ResetPasswordRequest,
    request: Request,
    response: Response,
    db: Session = _db_dep,
    limiter: InProcessRateLimiter = _limiter_dep,
) -> None:
    _rate_limit(limiter, request, body.token[:16])
    try:
        reset_password(
            db,
            request,
            response,
            token=body.token,
            new_password=body.newPassword,
        )
    except AuthError as exc:
        raise _auth_error_to_http(exc) from exc


@router.post("/api/v1/auth/password/change", status_code=204)
def change_password_endpoint(
    body: ChangePasswordRequest,
    request: Request,
    principal: CurrentPrincipal = _require_user_dep,
    db: Session = _db_dep,
    _csrf: None = _verify_csrf_dep,
) -> None:
    try:
        change_password(
            db,
            request,
            user_id=principal.user_id,  # type: ignore[arg-type]
            current_session_id=principal.session_id,
            current_password=body.currentPassword,
            new_password=body.newPassword,
        )
    except AuthError as exc:
        raise _auth_error_to_http(exc) from exc


# ============================================================
# /users/me routes
# ============================================================


@router.post("/api/v1/users/me/email-change/request", status_code=202)
def request_email_change_endpoint(
    body: EmailChangeRequest,
    request: Request,
    principal: CurrentPrincipal = _require_user_dep,
    db: Session = _db_dep,
    email_sender: EmailSender = _email_sender_dep,
    _csrf: None = _verify_csrf_dep,
    limiter: InProcessRateLimiter = _limiter_dep,
) -> dict:
    _rate_limit(limiter, request, body.newEmail)
    try:
        request_email_change(
            db,
            email_sender,
            user_id=principal.user_id,  # type: ignore[arg-type]
            new_email=body.newEmail,
            current_password=body.currentPassword,
        )
    except AuthError as exc:
        raise _auth_error_to_http(exc) from exc
    return {}


@router.post("/api/v1/users/me/email-change/confirm", status_code=204)
def confirm_email_change_endpoint(
    body: EmailChangeConfirmRequest,
    request: Request,
    response: Response,
    principal: CurrentPrincipal = _require_user_dep,
    db: Session = _db_dep,
    _csrf: None = _verify_csrf_dep,
) -> None:
    try:
        confirm_email_change(
            db,
            request,
            response,
            user_id=principal.user_id,  # type: ignore[arg-type]
            current_session_id=principal.session_id,
            token=body.token,
        )
    except AuthError as exc:
        raise _auth_error_to_http(exc) from exc


@router.get("/api/v1/users/me", response_model=UserResponse)
def get_me(
    principal: CurrentPrincipal = _require_user_dep,
    db: Session = _db_dep,
) -> UserResponse:
    user = db.query(User).filter(User.id == principal.user_id).first()
    if not user:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "auth.session_required",
                "message": "用户不存在",
                "fieldErrors": {},
            },
        )
    return UserResponse(
        id=user.id,
        displayName=user.display_name,
        email=user.email_display,
        emailVerified=user.email_verified_at is not None,
        status=user.status,
    )


@router.patch("/api/v1/users/me", response_model=UserResponse)
def update_me(
    body: UpdateProfileRequest,
    principal: CurrentPrincipal = _require_user_dep,
    db: Session = _db_dep,
    _csrf: None = _verify_csrf_dep,
) -> UserResponse:
    try:
        user = update_display_name(db, principal.user_id, body.displayName)  # type: ignore[arg-type]
    except AuthError as exc:
        raise _auth_error_to_http(exc) from exc
    return UserResponse(
        id=user.id,
        displayName=user.display_name,
        email=user.email_display,
        emailVerified=user.email_verified_at is not None,
        status=user.status,
    )


@router.delete("/api/v1/users/me", status_code=204)
def delete_me(
    body: DeleteAccountRequest,
    request: Request,
    response: Response,
    principal: CurrentPrincipal = _require_user_dep,
    db: Session = _db_dep,
    _csrf: None = _verify_csrf_dep,
) -> None:
    try:
        request_account_deletion(
            db,
            request,
            response,
            user_id=principal.user_id,  # type: ignore[arg-type]
            current_password=body.currentPassword,
            confirmation=body.confirmation,
        )
    except AuthError as exc:
        raise _auth_error_to_http(exc) from exc


@router.post("/api/v1/users/me/deletion/cancel", status_code=204)
def cancel_deletion(
    principal: CurrentPrincipal = _require_user_dep,
    db: Session = _db_dep,
    _csrf: None = _verify_csrf_dep,
) -> None:
    try:
        cancel_account_deletion(db, principal.user_id)  # type: ignore[arg-type]
    except AuthError as exc:
        raise _auth_error_to_http(exc) from exc
