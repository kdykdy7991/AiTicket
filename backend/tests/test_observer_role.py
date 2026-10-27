"""The observer sees global data and cannot mutate workflow state."""

from app.core.deps import get_current_user
from app.main import app
from app.models.ticket import Ticket
from app.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def test_observer_can_read_global_data_but_cannot_write(client):
    http, _, engine = client
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as db:
        db.add(Ticket(number="OBS-001", creator_id=1, owner_id=1,
                      customer_phone="13800138000", description="观察员可见的工单",
                      state="open", is_draft=False))
        await db.commit()
    created = await http.post("/api/v1/users", json={
        "username": "readonly-observer", "name": "只读观察员",
        "password": "observer-password", "role": "observer",
    })
    assert created.status_code == 201, created.text

    # Exercise the real JWT dependency rather than the admin fixture override.
    app.dependency_overrides.pop(get_current_user)
    login = await http.post("/api/v1/auth/login", json={
        "username": "readonly-observer", "password": "observer-password",
    })
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    for path in ("/api/v1/tickets", "/api/v1/visit-records", "/api/v1/users",
                 "/api/v1/groups", "/api/v1/skill-groups",
                 "/api/v1/stats/report", "/api/v1/stats/opportunity-analysis",
                 "/api/v1/sla-policies"):
        response = await http.get(path, headers=headers)
        assert response.status_code == 200, (path, response.text)
    knowledge = await http.get("/api/v1/knowledge/status", headers=headers)
    assert knowledge.status_code == 503  # No RAG service is configured for tests.
    tickets = await http.get("/api/v1/tickets", headers=headers)
    assert tickets.json()["data"][0]["number"] == "OBS-001"
    detail = await http.get("/api/v1/tickets/1", headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["allowed_actions"] == []
    assert detail.json()["can_reply"] is False

    denied = await http.post("/api/v1/visit-records", headers=headers, json={})
    assert denied.status_code == 403
    denied = await http.patch("/api/v1/users/1", headers=headers, json={"name": "changed"})
    assert denied.status_code == 403
    denied = await http.post("/api/v1/tickets", headers=headers, json={})
    assert denied.status_code == 403


async def test_observer_cannot_join_workflow_groups(client):
    http, _, _ = client
    response = await http.post("/api/v1/users", json={
        "username": "bad-observer", "name": "错误配置",
        "password": "observer-password", "role": "observer", "group_id": 1,
    })
    assert response.status_code == 422


async def test_assigned_user_must_hand_off_tickets_before_becoming_observer(client):
    http, _, engine = client
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as db:
        handler = User(username="assigned-handler", name="在途处理人",
                       password_hash="x", role="handler")
        db.add(handler)
        await db.flush()
        db.add(Ticket(number="OBS-002", creator_id=1, owner_id=handler.id,
                      customer_phone="13800138000", state="open"))
        await db.commit()
        handler_id = handler.id
    response = await http.patch(f"/api/v1/users/{handler_id}", json={"role": "observer"})
    assert response.status_code == 409


async def test_handler_can_become_observer_and_memberships_are_cleared(client):
    http, _, engine = client
    group = await http.post("/api/v1/groups", json={"name": "观察测试客服组"})
    department = await http.post("/api/v1/skill-groups", json={"name": "观察测试对接部门"})
    assert group.status_code == 201
    assert department.status_code == 201
    group_id = group.json()["data"]["id"]
    department_id = department.json()["data"]["id"]
    created = await http.post("/api/v1/users", json={
        "username": "former-handler", "name": "原处理人",
        "password": "observer-password", "role": "handler", "group_id": group_id,
        "skill_groups": [{"skill_group_id": department_id, "is_dispatcher": True}],
    })
    assert created.status_code == 201, created.text
    user_id = created.json()["data"]["id"]
    changed = await http.patch(f"/api/v1/users/{user_id}", json={
        "name": "原处理人", "role": "observer", "group_id": None,
        "skill_groups": [], "is_group_leader": False,
    })
    assert changed.status_code == 200, changed.text
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as db:
        user = await db.get(User, user_id)
        assert user.role == "observer" and user.group_id is None
    users = await http.get("/api/v1/users", params={"role": "observer"})
    assert users.json()["data"][0]["skill_groups"] == []
