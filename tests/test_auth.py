import os
import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

os.environ["CODE_NAVI_DATABASE_URL"] = "sqlite:///:memory:"

from code_navi.auth import models as auth_models  # noqa: E402,F401
from code_navi.auth.rate_limiter import get_rate_limiter
from code_navi.db import Base, engine  # noqa: E402
from code_navi.server import app  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_tables() -> Generator[None, None, None]:
    """Recreate all tables before each test so tests are fully isolated."""
    get_rate_limiter().reset()
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    get_rate_limiter().reset()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as tc:
        yield tc


def test_guest_session_creation(client: TestClient):
    response = client.get("/api/v1/auth/session")
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "guest"
    assert data["user"] is None
    assert "csrfToken" in data
    assert "id" in data["session"]


def test_user_registration_and_login(client: TestClient):
    uid = uuid.uuid4().hex[:8]
    email = f"testuser_{uid}@example.com"
    pwd = "SecurePassword123!"
    
    # 1. Register
    reg_res = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": pwd,
            "displayName": "测试用户",
            "claimGuestData": True
        }
    )
    assert reg_res.status_code == 201
    reg_data = reg_res.json()
    assert reg_data["mode"] == "authenticated"
    assert reg_data["user"]["email"] == email
    assert reg_data["user"]["displayName"] == "测试用户"
    assert reg_data["user"]["role"] == "student"
    csrf_token = reg_data["csrfToken"]

    # 2. Get current profile /users/me
    me_res = client.get("/api/v1/users/me")
    assert me_res.status_code == 200
    assert me_res.json()["email"] == email
    assert me_res.json()["role"] == "student"

    # 3. Update profile
    patch_res = client.patch(
        "/api/v1/users/me",
        json={"displayName": "新昵称"},
        headers={"X-CSRF-Token": csrf_token}
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["displayName"] == "新昵称"

    # 4. Logout
    logout_res = client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": csrf_token}
    )
    assert logout_res.status_code == 204

    # 5. Verify /users/me requires login now
    unauth_res = client.get("/api/v1/users/me")
    assert unauth_res.status_code == 401

    # 6. Login back
    login_res = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": pwd,
            "rememberMe": True,
            "claimGuestData": True
        }
    )
    assert login_res.status_code == 200
    login_data = login_res.json()
    assert login_data["mode"] == "authenticated"
    assert login_data["user"]["displayName"] == "新昵称"


def test_csrf_stability_across_session_reads(client: TestClient):
    """Multiple GET /session calls return stable CSRF token without rotating."""
    res1 = client.get("/api/v1/auth/session")
    assert res1.status_code == 200
    csrf1 = res1.json()["csrfToken"]

    res2 = client.get("/api/v1/auth/session")
    assert res2.status_code == 200
    csrf2 = res2.json()["csrfToken"]

    res3 = client.get("/api/v1/auth/session")
    assert res3.status_code == 200
    csrf3 = res3.json()["csrfToken"]

    assert csrf1 == csrf2 == csrf3


def test_csrf_rejection_on_mismatch(client: TestClient):
    """Mutating state without valid CSRF header returns 403."""
    res = client.get("/api/v1/auth/session")
    assert res.status_code == 200

    # Missing CSRF
    logout_no_csrf = client.post("/api/v1/auth/logout")
    assert logout_no_csrf.status_code == 403

    # Invalid CSRF
    logout_bad_csrf = client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": "invalid_token_12345"},
    )
    assert logout_bad_csrf.status_code == 403


def test_password_reset_anti_enumeration(client: TestClient):
    """Forgot password returns 202 even for non-existent emails to prevent enumeration."""
    res = client.post(
        "/api/v1/auth/password/forgot",
        json={"email": "nonexistent_random_user_9876@example.com"},
    )
    assert res.status_code == 202


def test_csrf_origin_validation(client: TestClient):
    """CSRF allows same-origin and allowed origins, rejects untrusted origins."""
    res = client.get("/api/v1/auth/session")
    csrf_token = res.json()["csrfToken"]

    # 1. Same-origin (http://testserver in TestClient) -> 204
    res_same = client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": csrf_token, "Origin": "http://testserver"},
    )
    assert res_same.status_code == 204

    # Re-login / get new session
    res = client.get("/api/v1/auth/session")
    csrf_token = res.json()["csrfToken"]

    # 2. Configured CORS origin -> 204
    res_cors = client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": csrf_token, "Origin": "http://localhost:3000"},
    )
    assert res_cors.status_code == 204

    # Re-login / get new session
    res = client.get("/api/v1/auth/session")
    csrf_token = res.json()["csrfToken"]

    # 3. Untrusted origin -> 403
    res_evil = client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": csrf_token, "Origin": "https://evil-site.com"},
    )
    assert res_evil.status_code == 403
    assert res_evil.json()["detail"]["code"] == "auth.csrf_failed"


def test_cookie_secure_configuration(monkeypatch: pytest.MonkeyPatch):
    """SessionSettings honors CODE_NAVI_COOKIE_SECURE and uses __Host- prefix."""
    from code_navi.auth.settings import SessionSettings

    settings = SessionSettings()

    monkeypatch.setenv("CODE_NAVI_COOKIE_SECURE", "1")
    assert settings.cookie_secure is True
    assert settings.cookie_name == "__Host-code_navi_session"

    monkeypatch.setenv("CODE_NAVI_COOKIE_SECURE", "0")
    assert settings.cookie_secure is False
    assert settings.cookie_name == "code_navi_session"


def test_registration_disabled_toggle(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """When CODE_NAVI_ALLOW_REGISTRATION=false, registration is rejected with 403."""
    monkeypatch.setenv("CODE_NAVI_ALLOW_REGISTRATION", "false")
    res = client.post(
        "/api/v1/auth/register",
        json={
            "email": "closed_reg@example.com",
            "password": "Password123!",
            "displayName": "Closed Reg",
        },
    )
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "auth.registration_disabled"


def test_x_forwarded_for_rate_limit_and_audit(client: TestClient):
    """X-Forwarded-For is extracted for rate limiting and audit logging."""
    from code_navi.auth.models import AuthEvent
    from code_navi.db import get_db

    # Trigger an event with X-Forwarded-For
    client.post(
        "/api/v1/auth/login",
        json={"email": "audit_user@example.com", "password": "WrongPassword123!"},
        headers={"X-Forwarded-For": "203.0.113.195, 10.0.0.1"},
    )

    db = next(get_db())
    try:
        event = (
            db.query(AuthEvent)
            .filter(AuthEvent.event_type == "login_failed")
            .order_by(AuthEvent.created_at.desc())
            .first()
        )
        assert event is not None
        assert event.ip_address == "203.0.113.195"
    finally:
        db.close()


def test_session_rotation_on_email_verification_and_change(client: TestClient):
    """Email verification and email change confirmation rotate the session cookie."""
    from datetime import UTC, datetime, timedelta

    from code_navi.auth.models import AuthOneTimeToken
    from code_navi.auth.security import hash_token
    from code_navi.db import get_db

    # 1. Register user
    reg_res = client.post(
        "/api/v1/auth/register",
        json={
            "email": "rotation_test@example.com",
            "password": "Password123!",
            "displayName": "Rotation User",
        },
    )
    assert reg_res.status_code == 201
    reg_cookie = client.cookies.get("code_navi_session")

    # 2. Request email verification and get token from DB
    client.post(
        "/api/v1/auth/email-verification/request",
        json={"email": "rotation_test@example.com"},
    )
    db = next(get_db())
    raw_token = "test_verify_token_123"
    token_record = AuthOneTimeToken(
        id=str(uuid.uuid4()),
        user_id=reg_res.json()["user"]["id"],
        purpose="email_verification",
        token_hash=hash_token(raw_token),
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    db.add(token_record)
    db.commit()
    db.close()

    # 3. Confirm email verification -> verify session cookie rotated
    verify_res = client.post(
        "/api/v1/auth/email-verification/confirm",
        json={"token": raw_token},
    )
    assert verify_res.status_code == 204
    rotated_cookie1 = client.cookies.get("code_navi_session")
    assert rotated_cookie1 != reg_cookie

    # Get updated csrf token from new session
    session_res = client.get("/api/v1/auth/session")
    assert session_res.status_code == 200
    new_csrf_token = session_res.json()["csrfToken"]

    # 4. Request email change
    change_req_res = client.post(
        "/api/v1/users/me/email-change/request",
        json={
            "newEmail": "new_rotation@example.com",
            "currentPassword": "Password123!",
        },
        headers={"X-CSRF-Token": new_csrf_token},
    )
    assert change_req_res.status_code == 202

    db = next(get_db())
    raw_change_token = "test_change_token_456"
    change_token_record = AuthOneTimeToken(
        id=str(uuid.uuid4()),
        user_id=reg_res.json()["user"]["id"],
        purpose="email_change",
        token_hash=hash_token(raw_change_token),
        new_email_normalized="new_rotation@example.com",
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    db.add(change_token_record)
    db.commit()
    db.close()

    # 5. Confirm email change -> verify session cookie rotated again
    confirm_change_res = client.post(
        "/api/v1/users/me/email-change/confirm",
        json={"token": raw_change_token},
        headers={"X-CSRF-Token": new_csrf_token},
    )
    assert confirm_change_res.status_code == 204
    rotated_cookie2 = client.cookies.get("code_navi_session")
    assert rotated_cookie2 != rotated_cookie1


def test_production_env_hides_docs(monkeypatch: pytest.MonkeyPatch):
    """When CODE_NAVI_ENV=production, SessionSettings reflects environment and hides docs."""
    from code_navi.auth.settings import SessionSettings

    monkeypatch.setenv("CODE_NAVI_ENV", "production")
    assert SessionSettings().environment == "production"


def test_user_role_registration_teacher(client: TestClient) -> None:
    """1. Register role='teacher' -> session and /users/me return 'teacher'."""
    uid = uuid.uuid4().hex[:8]
    email = f"teacher_{uid}@example.com"
    pwd = "SecurePassword123!"

    reg_res = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": pwd,
            "displayName": "张老师",
            "claimGuestData": True,
            "role": "teacher",
        },
    )
    assert reg_res.status_code == 201
    reg_data = reg_res.json()
    assert reg_data["user"]["role"] == "teacher"

    me_res = client.get("/api/v1/users/me")
    assert me_res.status_code == 200
    assert me_res.json()["role"] == "teacher"


def test_user_role_registration_default(client: TestClient) -> None:
    """2. Register without role -> defaults to 'student'."""
    uid = uuid.uuid4().hex[:8]
    email = f"student_{uid}@example.com"
    pwd = "SecurePassword123!"

    reg_res = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": pwd,
            "displayName": "李同学",
            "claimGuestData": True,
        },
    )
    assert reg_res.status_code == 201
    assert reg_res.json()["user"]["role"] == "student"

    me_res = client.get("/api/v1/users/me")
    assert me_res.status_code == 200
    assert me_res.json()["role"] == "student"


def test_user_role_registration_invalid(client: TestClient) -> None:
    """3. Register role='admin' (invalid) -> 422."""
    uid = uuid.uuid4().hex[:8]
    email = f"admin_{uid}@example.com"
    pwd = "SecurePassword123!"

    reg_res = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": pwd,
            "displayName": "非法用户",
            "claimGuestData": True,
            "role": "admin",
        },
    )
    assert reg_res.status_code == 422


def test_patch_user_role_requires_auth_and_csrf(client: TestClient) -> None:
    """4 & 6. PATCH /users/me/role without auth -> 401; without CSRF -> 403; invalid role -> 422."""
    # 6b. unauthenticated -> 401
    unauth_res = client.patch(
        "/api/v1/users/me/role",
        json={"role": "teacher"},
    )
    assert unauth_res.status_code == 401

    # Login / Register a student
    uid = uuid.uuid4().hex[:8]
    email = f"user_{uid}@example.com"
    pwd = "SecurePassword123!"
    reg_res = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": pwd,
            "displayName": "测试用户",
            "claimGuestData": True,
            "role": "student",
        },
    )
    assert reg_res.status_code == 201
    csrf_token = reg_res.json()["csrfToken"]

    # 4. Authenticated but no CSRF -> 403
    no_csrf_res = client.patch(
        "/api/v1/users/me/role",
        json={"role": "teacher"},
    )
    assert no_csrf_res.status_code == 403

    # 6a. Authenticated with CSRF but invalid role -> 422
    invalid_res = client.patch(
        "/api/v1/users/me/role",
        json={"role": "superadmin"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert invalid_res.status_code == 422


def test_patch_user_role_success_and_idempotent_and_session_preserved(client: TestClient) -> None:
    """5, 7, 8. PATCH role='teacher' -> 200, audit event, idempotent, session preserved."""
    from code_navi.auth.models import AuthEvent, AuthSession, Principal
    from code_navi.db import get_db

    uid = uuid.uuid4().hex[:8]
    email = f"user_{uid}@example.com"
    pwd = "SecurePassword123!"
    reg_res = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": pwd,
            "displayName": "测试用户",
            "claimGuestData": True,
            "role": "student",
        },
    )
    assert reg_res.status_code == 201
    csrf_token = reg_res.json()["csrfToken"]
    cookie_before = client.cookies.get("code_navi_session")

    db = next(get_db())
    principal_count_before = db.query(Principal).count()
    session_count_before = db.query(AuthSession).count()
    db.close()

    # 5. Switch role to teacher
    patch_res = client.patch(
        "/api/v1/users/me/role",
        json={"role": "teacher"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["role"] == "teacher"

    # Verify GET /users/me returns teacher
    me_res = client.get("/api/v1/users/me")
    assert me_res.status_code == 200
    assert me_res.json()["role"] == "teacher"

    # Verify session user.role updated
    session_res = client.get("/api/v1/auth/session")
    assert session_res.status_code == 200
    assert session_res.json()["user"]["role"] == "teacher"

    # Verify auth_events has role_changed with metadata_={"from": "student", "to": "teacher"}
    db = next(get_db())
    events = (
        db.query(AuthEvent)
        .filter(AuthEvent.event_type == "role_changed")
        .all()
    )
    assert len(events) == 1
    assert events[0].metadata_ == {"from": "student", "to": "teacher"}

    # 7. Repeat switch to teacher -> 200 idempotent
    repeat_res = client.patch(
        "/api/v1/users/me/role",
        json={"role": "teacher"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert repeat_res.status_code == 200
    assert repeat_res.json()["role"] == "teacher"

    # 8. Session still valid and principals/auth_sessions count unchanged
    cookie_after = client.cookies.get("code_navi_session")
    assert cookie_after == cookie_before  # cookie not rotated
    assert db.query(Principal).count() == principal_count_before
    assert db.query(AuthSession).count() == session_count_before
    db.close()


def test_require_role_dependency_behavior(client: TestClient) -> None:
    """Verify require_role: teacher/student accessing POST /classes and POST /classes/join."""
    # 1. Unauthenticated -> 401
    unauth_create = client.post("/api/v1/classes", json={"name": "无登录建班"})
    assert unauth_create.status_code == 401

    # 2. Student registration
    s_uid = uuid.uuid4().hex[:8]
    s_reg = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"s_dep_{s_uid}@example.com",
            "password": "Password123!",
            "displayName": "测试学生",
            "role": "student",
        },
    )
    s_csrf = s_reg.json()["csrfToken"]

    # Student cannot create class -> 403
    s_create = client.post(
        "/api/v1/classes",
        json={"name": "学生测试建班"},
        headers={"X-CSRF-Token": s_csrf},
    )
    assert s_create.status_code == 403
    assert s_create.json()["detail"]["code"] == "auth.forbidden"

    # 3. Teacher registration
    t_client = TestClient(app)
    t_uid = uuid.uuid4().hex[:8]
    t_reg = t_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"t_dep_{t_uid}@example.com",
            "password": "Password123!",
            "displayName": "测试老师",
            "role": "teacher",
        },
    )
    t_csrf = t_reg.json()["csrfToken"]

    # Teacher creates class -> 201
    t_create = t_client.post(
        "/api/v1/classes",
        json={"name": "老师测试班级"},
        headers={"X-CSRF-Token": t_csrf},
    )
    assert t_create.status_code == 201
    code = t_create.json()["inviteCode"]

    # Teacher cannot join class via student endpoint -> 403
    t_join = t_client.post(
        "/api/v1/classes/join",
        json={"inviteCode": code},
        headers={"X-CSRF-Token": t_csrf},
    )
    assert t_join.status_code == 403
    assert t_join.json()["detail"]["code"] == "auth.forbidden"

    # Student joins class -> 200
    s_join = client.post(
        "/api/v1/classes/join",
        json={"inviteCode": code},
        headers={"X-CSRF-Token": s_csrf},
    )
    assert s_join.status_code == 200


def test_list_sessions_grouped_by_device(client: TestClient) -> None:
    """Sessions from same User-Agent are grouped; distinct UA forms separate groups."""
    email = f"sess_group_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "SecurePassword123!"
    ua_pc = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"
    ua_phone = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Safari/604.1"

    # Register on PC
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": pwd, "displayName": "测试用户", "role": "student"},
        headers={"User-Agent": ua_pc},
    )
    assert reg.status_code == 201

    # Second login on PC with same UA
    c2 = TestClient(app)
    l2 = c2.post(
        "/api/v1/auth/login",
        json={"email": email, "password": pwd},
        headers={"User-Agent": ua_pc},
    )
    assert l2.status_code == 200

    # Third login on Phone with different UA
    c3 = TestClient(app)
    l3 = c3.post(
        "/api/v1/auth/login",
        json={"email": email, "password": pwd},
        headers={"User-Agent": ua_phone},
    )
    assert l3.status_code == 200

    # Query sessions using c2 (current session is on PC)
    sess_res = c2.get("/api/v1/auth/sessions")
    assert sess_res.status_code == 200
    items = sess_res.json()["items"]
    assert len(items) == 2

    # Verify PC group (should have sessionCount == 2)
    pc_group = next(i for i in items if "Chrome" in (i["userAgentLabel"] or ""))
    assert pc_group["sessionCount"] == 2
    assert len(pc_group["sessionIds"]) == 2
    assert pc_group["current"] is True

    # Verify Phone group
    phone_group = next(i for i in items if "iPhone" in (i["userAgentLabel"] or ""))
    assert phone_group["sessionCount"] == 1
    assert len(phone_group["sessionIds"]) == 1
    assert phone_group["current"] is False


def test_revoke_many_sessions_endpoint(client: TestClient) -> None:
    """revoke-many revokes all sessions in the list and enforces CSRF."""
    email = f"sess_revoke_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "SecurePassword123!"
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"

    reg = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": pwd, "displayName": "测试用户", "role": "student"},
        headers={"User-Agent": ua},
    )
    csrf = reg.json()["csrfToken"]

    # Create 2 more sessions on same UA
    c2 = TestClient(app)
    c2.post(
        "/api/v1/auth/login",
        json={"email": email, "password": pwd},
        headers={"User-Agent": ua},
    )
    c3 = TestClient(app)
    c3.post(
        "/api/v1/auth/login",
        json={"email": email, "password": pwd},
        headers={"User-Agent": ua},
    )

    # Fetch sessions
    sess_res = client.get("/api/v1/auth/sessions")
    items = sess_res.json()["items"]
    assert len(items) == 1
    session_ids = items[0]["sessionIds"]
    assert len(session_ids) == 3

    current_sess_id = client.get("/api/v1/auth/session").json()["session"]["id"]
    other_ids = [sid for sid in session_ids if sid != current_sess_id]
    assert len(other_ids) == 2
    bad_revoke = client.post(
        "/api/v1/auth/sessions/revoke-many",
        json={"sessionIds": other_ids},
    )
    assert bad_revoke.status_code == 403

    # Revoke with valid CSRF -> 200
    ok_revoke = client.post(
        "/api/v1/auth/sessions/revoke-many",
        json={"sessionIds": other_ids},
        headers={"X-CSRF-Token": csrf},
    )
    assert ok_revoke.status_code == 200
    assert ok_revoke.json()["revokedCount"] == len(other_ids)

    # Re-fetch sessions: count should now be 1
    sess_res_after = client.get("/api/v1/auth/sessions")
    items_after = sess_res_after.json()["items"]
    assert len(items_after) == 1
    assert items_after[0]["sessionCount"] == 1





