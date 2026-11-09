"""Password change audit: who changed whose password, when and from where."""

from app.core.deps import get_current_user
from app.core.security import hash_password
from app.main import app
from app.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def _headers(response):
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def _fake_admin():
    return type("_FakeAdmin", (), {
        "id": 1, "group_id": None, "role": "admin",
        "is_active": True, "username": "test-admin",
    })()


async def _login(http, username, password):
    app.dependency_overrides.pop(get_current_user, None)
    response = await http.post("/api/v1/auth/login", json={
        "username": username, "password": password,
    })
    assert response.status_code == 200, response.text
    return response


async def _create_user(engine, username, role="observer", password="old-password"):
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as db:
        user = User(
            username=username, name=username, role=role,
            password_hash=hash_password(password), local_login_enabled=True,
        )
        db.add(user)
        await db.commit()
        return user.id


async def test_self_service_password_change_is_audited(client):
    http, _, engine = client
    uid = await _create_user(engine, "pw-self")

    login = await _login(http, "pw-self", "old-password")
    changed = await http.post(
        "/api/v1/auth/change-password", headers=_headers(login),
        json={"old_password": "old-password", "new_password": "new-password"},
    )
    assert changed.status_code == 200, changed.text

    app.dependency_overrides[get_current_user] = _fake_admin
    logs = await http.get("/api/v1/password-change-logs", params={"user_id": uid})
    assert logs.status_code == 200, logs.text
    rows = logs.json()["data"]
    assert len(rows) == 1
    row = rows[0]
    assert row["method"] == "self" and row["method_label"] == "本人修改"
    assert row["actor_id"] == uid and row["target_id"] == uid
    assert row["actor_name"] == "pw-self" and row["target_name"] == "pw-self"
    assert row["created_at"]
    # The password really changed (a fresh login with the new one succeeds).
    assert (await _login(http, "pw-self", "new-password")).status_code == 200


async def test_admin_reset_is_audited_and_plain_edit_is_not(client):
    http, _, engine = client
    uid = await _create_user(engine, "pw-admin-target")
    app.dependency_overrides[get_current_user] = _fake_admin

    edited = await http.patch(f"/api/v1/users/{uid}", json={"name": "只改名字"})
    assert edited.status_code == 200, edited.text
    assert (await http.get("/api/v1/password-change-logs")).json()["data"] == []

    reset = await http.patch(f"/api/v1/users/{uid}", json={"password": "brand-new-password"})
    assert reset.status_code == 200, reset.text
    logs = await http.get("/api/v1/password-change-logs", params={"user_id": uid})
    assert logs.status_code == 200, logs.text
    rows = logs.json()["data"]
    assert len(rows) == 1
    row = rows[0]
    assert row["method"] == "admin" and row["method_label"] == "管理员重置"
    assert row["actor_id"] == 1 and row["target_id"] == uid
    assert row["actor_name"] == "test-admin" and row["target_name"] == "pw-admin-target"
    assert row["created_at"]

    filtered = await http.get("/api/v1/password-change-logs", params={"user_id": 999999})
    assert filtered.json()["data"] == []


async def test_non_admin_cannot_read_password_logs(client):
    http, _, engine = client
    await _create_user(engine, "pw-reader", password="test-password")
    login = await _login(http, "pw-reader", "test-password")
    resp = await http.get("/api/v1/password-change-logs", headers=_headers(login))
    assert resp.status_code == 403
