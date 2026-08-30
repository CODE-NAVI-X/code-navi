"""Tests for classroom management: creation, invite codes, joining, members, role switching."""

from __future__ import annotations

import os
import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

os.environ["CODE_NAVI_DATABASE_URL"] = "sqlite:///:memory:"

from code_navi.auth import models as auth_models  # noqa: E402,F401
from code_navi.auth.models import AuthEvent
from code_navi.auth.rate_limiter import get_rate_limiter  # noqa: E402
from code_navi.classroom import models as classroom_models  # noqa: E402,F401
from code_navi.classroom.service import INVITE_CODE_CHARACTERS
from code_navi.db import Base, engine, get_db  # noqa: E402
from code_navi.server import app  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_tables() -> Generator[None, None, None]:
    """Recreate all tables before each test for total isolation."""
    get_rate_limiter().reset()
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    get_rate_limiter().reset()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as tc:
        yield tc


def _register(client: TestClient, role: str, name: str) -> dict:
    uid = uuid.uuid4().hex[:8]
    email = f"{role}_{uid}@example.com"
    res = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "SecurePassword123!",
            "displayName": name,
            "claimGuestData": False,
            "role": role,
        },
    )
    assert res.status_code == 201
    return res.json()


def test_teacher_create_classroom_success(client: TestClient) -> None:
    """1. Teacher creates class: invite code generated, owner is teacher member."""
    reg = _register(client, "teacher", "王老师")
    csrf_token = reg["csrfToken"]

    res = client.post(
        "/api/v1/classes",
        json={"name": "计算机系统导论"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "计算机系统导论"
    assert data["roleInClass"] == "teacher"
    assert data["isOwner"] is True
    assert data["memberCount"] == 1
    assert data["inviteCode"] is not None
    assert len(data["inviteCode"]) == 8
    assert all(ch in INVITE_CODE_CHARACTERS for ch in data["inviteCode"])

    # Check list endpoint
    list_res = client.get("/api/v1/classes")
    assert list_res.status_code == 200
    items = list_res.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == data["id"]
    assert items[0]["inviteCode"] == data["inviteCode"]

    # Check audit event
    db = next(get_db())
    event = (
        db.query(AuthEvent)
        .filter(AuthEvent.event_type == "class_created")
        .first()
    )
    assert event is not None
    assert event.metadata_["class_name"] == "计算机系统导论"
    db.close()


def test_student_join_classroom_and_tolerances(client: TestClient) -> None:
    """2. Student joins by code: lowercase/spaces tolerated, duplicate 409, invalid 404."""
    # Teacher creates class
    teacher_reg = _register(client, "teacher", "张老师")
    create_res = client.post(
        "/api/v1/classes",
        json={"name": "数据结构与算法"},
        headers={"X-CSRF-Token": teacher_reg["csrfToken"]},
    )
    assert create_res.status_code == 201
    invite_code = create_res.json()["inviteCode"]
    class_id = create_res.json()["id"]

    # Switch to student client
    student_client = TestClient(app)
    student_reg = _register(student_client, "student", "李同学")
    student_csrf = student_reg["csrfToken"]

    # Tolerant join with lowercase and whitespace
    join_res = student_client.post(
        "/api/v1/classes/join",
        json={"inviteCode": f"  {invite_code.lower()}  "},
        headers={"X-CSRF-Token": student_csrf},
    )
    assert join_res.status_code == 200
    join_data = join_res.json()
    assert join_data["id"] == class_id
    assert join_data["name"] == "数据结构与算法"
    assert join_data["roleInClass"] == "student"
    assert join_data["isOwner"] is False
    assert join_data["memberCount"] == 2
    assert join_data["inviteCode"] is None  # Non-owner does not see invite code

    # Duplicate join -> 409
    dup_res = student_client.post(
        "/api/v1/classes/join",
        json={"inviteCode": invite_code},
        headers={"X-CSRF-Token": student_csrf},
    )
    assert dup_res.status_code == 409
    assert dup_res.json()["detail"]["code"] == "class.already_member"

    # Invalid code -> 404
    inv_res = student_client.post(
        "/api/v1/classes/join",
        json={"inviteCode": "NONEXIST8"},
        headers={"X-CSRF-Token": student_csrf},
    )
    assert inv_res.status_code == 404
    assert inv_res.json()["detail"]["code"] == "class.invalid_invite_code"

    # Check audit event
    db = next(get_db())
    event = (
        db.query(AuthEvent)
        .filter(AuthEvent.event_type == "class_joined")
        .first()
    )
    assert event is not None
    assert event.metadata_["class_id"] == class_id
    db.close()


def test_role_restrictions_on_classroom_endpoints(client: TestClient) -> None:
    """3. Student creating class -> 403; Teacher joining class -> 403."""
    teacher_client = TestClient(app)
    t_reg = _register(teacher_client, "teacher", "导师")
    c_res = teacher_client.post(
        "/api/v1/classes",
        json={"name": "操作系统"},
        headers={"X-CSRF-Token": t_reg["csrfToken"]},
    )
    assert c_res.status_code == 201
    code = c_res.json()["inviteCode"]

    # Student cannot create class -> 403
    student_client = TestClient(app)
    s_reg = _register(student_client, "student", "学徒")
    s_create = student_client.post(
        "/api/v1/classes",
        json={"name": "学生自己建的班"},
        headers={"X-CSRF-Token": s_reg["csrfToken"]},
    )
    assert s_create.status_code == 403
    assert s_create.json()["detail"]["code"] == "auth.forbidden"

    # Teacher cannot join class via student endpoint -> 403
    t_join = teacher_client.post(
        "/api/v1/classes/join",
        json={"inviteCode": code},
        headers={"X-CSRF-Token": t_reg["csrfToken"]},
    )
    assert t_join.status_code == 403
    assert t_join.json()["detail"]["code"] == "auth.forbidden"


def test_csrf_protection_on_create_and_join(client: TestClient) -> None:
    """4. POST /classes and POST /classes/join require valid CSRF token."""
    teacher_client = TestClient(app)
    t_reg = _register(teacher_client, "teacher", "周老师")

    # Create without CSRF -> 403
    no_csrf_create = teacher_client.post(
        "/api/v1/classes",
        json={"name": "编译原理"},
    )
    assert no_csrf_create.status_code == 403

    # Now create with CSRF
    ok_create = teacher_client.post(
        "/api/v1/classes",
        json={"name": "编译原理"},
        headers={"X-CSRF-Token": t_reg["csrfToken"]},
    )
    assert ok_create.status_code == 201
    code = ok_create.json()["inviteCode"]

    # Student join without CSRF -> 403
    student_client = TestClient(app)
    _register(student_client, "student", "赵同学")
    no_csrf_join = student_client.post(
        "/api/v1/classes/join",
        json={"inviteCode": code},
    )
    assert no_csrf_join.status_code == 403


def test_get_single_classroom_access_control(client: TestClient) -> None:
    """5. GET /classes/{id}: owner sees inviteCode, member does not, outsider gets 404."""
    # 1. Teacher creates class
    teacher_client = TestClient(app)
    t_reg = _register(teacher_client, "teacher", "钱老师")
    create_res = teacher_client.post(
        "/api/v1/classes",
        json={"name": "计算机网络"},
        headers={"X-CSRF-Token": t_reg["csrfToken"]},
    )
    assert create_res.status_code == 201
    class_id = create_res.json()["id"]
    invite_code = create_res.json()["inviteCode"]

    # 2. Student joins
    student_client = TestClient(app)
    s_reg = _register(student_client, "student", "孙同学")
    join_res = student_client.post(
        "/api/v1/classes/join",
        json={"inviteCode": invite_code},
        headers={"X-CSRF-Token": s_reg["csrfToken"]},
    )
    assert join_res.status_code == 200

    # 3. Owner gets class -> 200, inviteCode present
    owner_get = teacher_client.get(f"/api/v1/classes/{class_id}")
    assert owner_get.status_code == 200
    assert owner_get.json()["inviteCode"] == invite_code
    assert owner_get.json()["isOwner"] is True

    # 4. Member student gets class -> 200, inviteCode is None
    member_get = student_client.get(f"/api/v1/classes/{class_id}")
    assert member_get.status_code == 200
    assert member_get.json()["inviteCode"] is None
    assert member_get.json()["isOwner"] is False
    assert member_get.json()["roleInClass"] == "student"

    # 5. Outsider student gets class -> 404
    outsider_client = TestClient(app)
    _register(outsider_client, "student", "外人")
    outsider_get = outsider_client.get(f"/api/v1/classes/{class_id}")
    assert outsider_get.status_code == 404
    assert outsider_get.json()["detail"]["code"] == "class.not_found"


def test_list_members_privacy_and_access_control(client: TestClient) -> None:
    """6. Members list: readable by owner and member, 404 for outsider, does NOT expose emails."""
    teacher_client = TestClient(app)
    t_reg = _register(teacher_client, "teacher", "吴老师")
    create_res = teacher_client.post(
        "/api/v1/classes",
        json={"name": "人工智能基础"},
        headers={"X-CSRF-Token": t_reg["csrfToken"]},
    )
    class_id = create_res.json()["id"]
    code = create_res.json()["inviteCode"]

    student_client = TestClient(app)
    s_reg = _register(student_client, "student", "郑同学")
    student_client.post(
        "/api/v1/classes/join",
        json={"inviteCode": code},
        headers={"X-CSRF-Token": s_reg["csrfToken"]},
    )

    # Owner lists members
    t_members = teacher_client.get(f"/api/v1/classes/{class_id}/members")
    assert t_members.status_code == 200
    items = t_members.json()["items"]
    assert len(items) == 2

    # Teacher should appear first
    assert items[0]["displayName"] == "吴老师"
    assert items[0]["roleInClass"] == "teacher"
    assert items[1]["displayName"] == "郑同学"
    assert items[1]["roleInClass"] == "student"

    # Owner sees emails
    for item in items:
        assert item["email"] is not None
        assert "inviteCode" not in item

    # Member lists members -> 200, but email and note are None
    s_members = student_client.get(f"/api/v1/classes/{class_id}/members")
    assert s_members.status_code == 200
    s_items = s_members.json()["items"]
    assert len(s_items) == 2
    for item in s_items:
        assert item.get("email") is None
        assert item.get("note") is None

    # Outsider lists members -> 404
    outsider_client = TestClient(app)
    _register(outsider_client, "student", "无关人员")
    out_members = outsider_client.get(f"/api/v1/classes/{class_id}/members")
    assert out_members.status_code == 404
    assert out_members.json()["detail"]["code"] == "class.not_found"


def test_role_switch_preserves_classroom_membership(client: TestClient) -> None:
    """7. Switching role (student <-> teacher) does not alter class ownership or membership."""
    teacher_client = TestClient(app)
    t_reg = _register(teacher_client, "teacher", "沈老师")
    create_res = teacher_client.post(
        "/api/v1/classes",
        json={"name": "分布式系统"},
        headers={"X-CSRF-Token": t_reg["csrfToken"]},
    )
    class_id = create_res.json()["id"]
    code = create_res.json()["inviteCode"]

    student_client = TestClient(app)
    s_reg = _register(student_client, "student", "韩同学")
    student_client.post(
        "/api/v1/classes/join",
        json={"inviteCode": code},
        headers={"X-CSRF-Token": s_reg["csrfToken"]},
    )

    # 1. Student switches role to teacher
    switch_res = student_client.patch(
        "/api/v1/users/me/role",
        json={"role": "teacher"},
        headers={"X-CSRF-Token": s_reg["csrfToken"]},
    )
    assert switch_res.status_code == 200
    assert switch_res.json()["role"] == "teacher"

    # Student (now role=teacher) still has the class in list:
    # isOwner is False, roleInClass is student
    s_list = student_client.get("/api/v1/classes")
    assert s_list.status_code == 200
    s_classes = s_list.json()["items"]
    assert len(s_classes) == 1
    assert s_classes[0]["id"] == class_id
    assert s_classes[0]["isOwner"] is False
    assert s_classes[0]["roleInClass"] == "student"

    # 2. Teacher switches role to student
    t_switch = teacher_client.patch(
        "/api/v1/users/me/role",
        json={"role": "student"},
        headers={"X-CSRF-Token": t_reg["csrfToken"]},
    )
    assert t_switch.status_code == 200
    assert t_switch.json()["role"] == "student"

    # Teacher (now role=student) still has the class, isOwner is True, roleInClass is teacher
    t_list = teacher_client.get("/api/v1/classes")
    assert t_list.status_code == 200
    t_classes = t_list.json()["items"]
    assert len(t_classes) == 1
    assert t_classes[0]["id"] == class_id
    assert t_classes[0]["isOwner"] is True
    assert t_classes[0]["roleInClass"] == "teacher"
    assert t_classes[0]["inviteCode"] == code


def test_classroom_member_note_crud_and_remove(client: TestClient) -> None:
    """8. Teacher manages student note and can remove student from class."""
    teacher_client = TestClient(app)
    t_reg = _register(teacher_client, "teacher", "徐老师")
    create_res = teacher_client.post(
        "/api/v1/classes",
        json={"name": "操作系统实验班"},
        headers={"X-CSRF-Token": t_reg["csrfToken"]},
    )
    class_id = create_res.json()["id"]
    code = create_res.json()["inviteCode"]

    student_client = TestClient(app)
    s_reg = _register(student_client, "student", "韩同学")
    join_res = student_client.post(
        "/api/v1/classes/join",
        json={"inviteCode": code},
        headers={"X-CSRF-Token": s_reg["csrfToken"]},
    )
    assert join_res.status_code == 200
    student_user_id = s_reg["user"]["id"]
    teacher_user_id = t_reg["user"]["id"]

    # Teacher updates note on student
    patch_res = teacher_client.patch(
        f"/api/v1/classes/{class_id}/members/{student_user_id}",
        json={"note": "平时作业积极，代码规范好"},
        headers={"X-CSRF-Token": t_reg["csrfToken"]},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["note"] == "平时作业积极，代码规范好"

    # Teacher reads members: note is visible
    t_members = teacher_client.get(f"/api/v1/classes/{class_id}/members").json()["items"]
    student_item = next(i for i in t_members if i["userId"] == student_user_id)
    assert student_item["note"] == "平时作业积极，代码规范好"
    assert student_item["email"] is not None

    # Student reads members: note is NOT visible (None)
    s_members = student_client.get(f"/api/v1/classes/{class_id}/members").json()["items"]
    s_student_item = next(i for i in s_members if i["userId"] == student_user_id)
    assert s_student_item.get("note") is None
    assert s_student_item.get("email") is None

    # Student tries to update note -> 404
    s_patch = student_client.patch(
        f"/api/v1/classes/{class_id}/members/{student_user_id}",
        json={"note": "恶意修改"},
        headers={"X-CSRF-Token": s_reg["csrfToken"]},
    )
    assert s_patch.status_code == 404

    # Teacher tries to delete self -> 400
    del_self = teacher_client.delete(
        f"/api/v1/classes/{class_id}/members/{teacher_user_id}",
        headers={"X-CSRF-Token": t_reg["csrfToken"]},
    )
    assert del_self.status_code == 400

    # Student tries to delete member -> 404
    del_by_student = student_client.delete(
        f"/api/v1/classes/{class_id}/members/{student_user_id}",
        headers={"X-CSRF-Token": s_reg["csrfToken"]},
    )
    assert del_by_student.status_code == 404

    # Teacher removes student -> 204
    del_student = teacher_client.delete(
        f"/api/v1/classes/{class_id}/members/{student_user_id}",
        headers={"X-CSRF-Token": t_reg["csrfToken"]},
    )
    assert del_student.status_code == 204

    # Classroom member count is now 1
    t_classes = teacher_client.get("/api/v1/classes").json()["items"]
    assert t_classes[0]["memberCount"] == 1

    # Student list of classes is now empty
    s_classes = student_client.get("/api/v1/classes").json()["items"]
    assert len(s_classes) == 0

    # Student can rejoin using invite code
    rejoin = student_client.post(
        "/api/v1/classes/join",
        json={"inviteCode": code},
        headers={"X-CSRF-Token": s_reg["csrfToken"]},
    )
    assert rejoin.status_code == 200
