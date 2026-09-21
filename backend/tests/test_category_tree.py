"""Phase 1 tests: deep category tree, cycle detection, level derivation."""

import pytest
from sqlalchemy import select

from app.models.category import TicketCategory
from app.models.user import User


async def _admin_headers(c, admin_id: int) -> dict:
    """Override auth dep with admin user — bypass login."""
    return {}


@pytest.fixture
async def admin_user(client):
    c, dispatcher_id, engine = client
    from app.models.user import User
    from app.core.deps import get_current_user
    from app.main import app

    async def fake_admin():
        u = type("_U", (), {"id": 1, "role": "admin", "is_active": True, "group_id": None})()
        return u

    app.dependency_overrides[get_current_user] = fake_admin
    yield c
    app.dependency_overrides.pop(get_current_user, None)


async def test_create_top_level_category(admin_user):
    resp = await admin_user.post("/api/v1/categories", json={"name": "顶层A"})
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["level"] == 1
    assert data["parent_id"] is None


async def test_create_three_levels(admin_user):
    """Chain: A (L1) -> A1 (L2) -> A1-i (L3) -> A1-i-x (L4)."""
    a = (await admin_user.post("/api/v1/categories", json={"name": "A"})).json()["data"]
    a1 = (await admin_user.post("/api/v1/categories", json={"name": "A1", "parent_id": a["id"]})).json()["data"]
    assert a1["level"] == 2
    a1i = (await admin_user.post("/api/v1/categories", json={"name": "A1-i", "parent_id": a1["id"]})).json()["data"]
    assert a1i["level"] == 3
    a1ix = (await admin_user.post("/api/v1/categories", json={"name": "A1-i-x", "parent_id": a1i["id"]})).json()["data"]
    assert a1ix["level"] == 4


async def test_list_categories_returns_path_and_depth(admin_user):
    a = (await admin_user.post("/api/v1/categories", json={"name": "咨询"})).json()["data"]
    b = (await admin_user.post("/api/v1/categories", json={"name": "即时", "parent_id": a["id"]})).json()["data"]
    c = (await admin_user.post("/api/v1/categories", json={"name": "即时办结咨询", "parent_id": b["id"]})).json()["data"]

    resp = await admin_user.get("/api/v1/categories")
    assert resp.status_code == 200
    tree = resp.json()["data"]
    assert len(tree) == 1
    assert tree[0]["name"] == "咨询"
    assert tree[0]["level"] == 1
    assert tree[0]["path"] == "咨询"
    leaf = tree[0]["children"][0]["children"][0]
    assert leaf["name"] == "即时办结咨询"
    assert leaf["level"] == 3
    assert leaf["path"] == "咨询 / 即时 / 即时办结咨询"


async def test_cannot_parent_to_self_or_descendant(admin_user):
    a = (await admin_user.post("/api/v1/categories", json={"name": "X"})).json()["data"]
    a1 = (await admin_user.post("/api/v1/categories", json={"name": "X1", "parent_id": a["id"]})).json()["data"]
    a2 = (await admin_user.post("/api/v1/categories", json={"name": "X2", "parent_id": a1["id"]})).json()["data"]

    # 自指
    r = await admin_user.patch(f"/api/v1/categories/{a['id']}", json={"parent_id": a["id"]})
    assert r.status_code == 400, r.text

    # 指到子孙
    r = await admin_user.patch(f"/api/v1/categories/{a['id']}", json={"parent_id": a2["id"]})
    assert r.status_code == 400, r.text


async def test_parent_change_recomputes_descendant_levels(admin_user):
    a = (await admin_user.post("/api/v1/categories", json={"name": "P"})).json()["data"]
    b = (await admin_user.post("/api/v1/categories", json={"name": "Q"})).json()["data"]
    c1 = (await admin_user.post("/api/v1/categories", json={"name": "C1", "parent_id": a["id"]})).json()["data"]
    c2 = (await admin_user.post("/api/v1/categories", json={"name": "C2", "parent_id": c1["id"]})).json()["data"]
    # Initially C1.level=2, C2.level=3
    assert c1["level"] == 2 and c2["level"] == 3

    # Move C1 to be child of Q (also L1). C1->2, C2->3 still (because level is depth, not unique).
    r = await admin_user.patch(f"/api/v1/categories/{c1['id']}", json={"parent_id": b["id"]})
    assert r.status_code == 200, r.text
    tree = (await admin_user.get("/api/v1/categories")).json()["data"]
    q_node = next(n for n in tree if n["name"] == "Q")
    c1_node = next(n for n in q_node["children"] if n["name"] == "C1")
    c2_node = c1_node["children"][0]
    assert c1_node["level"] == 2
    assert c2_node["level"] == 3


async def test_delete_with_children_fails(admin_user):
    a = (await admin_user.post("/api/v1/categories", json={"name": "R"})).json()["data"]
    a1 = (await admin_user.post("/api/v1/categories", json={"name": "R1", "parent_id": a["id"]})).json()["data"]
    r = await admin_user.delete(f"/api/v1/categories/{a['id']}")
    assert r.status_code == 400


async def test_delete_leaf_succeeds(admin_user):
    a = (await admin_user.post("/api/v1/categories", json={"name": "S"})).json()["data"]
    r = await admin_user.delete(f"/api/v1/categories/{a['id']}")
    assert r.status_code == 200


async def test_legacy_two_level_categories_still_work(client):
    """回滚：旧的 2 级分类（API 旧版本写入的数据）在新的 API 下能正常 list。"""
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.models.category import TicketCategory

    c, dispatcher_id, engine = client
    async with AsyncSession(engine) as s:
        s.add(TicketCategory(name="旧一级", parent_id=None, level=1, sort_order=0, is_active=True))
        await s.flush()
        l1_id = (await s.execute(select(TicketCategory).order_by(TicketCategory.id.desc()).limit(1))).scalar_one().id
        s.add(TicketCategory(name="旧二级", parent_id=l1_id, level=2, sort_order=0, is_active=True))
        await s.commit()
    resp = await c.get("/api/v1/categories")
    assert resp.status_code == 200
    tree = resp.json()["data"]
    names = [n["name"] for n in tree]
    assert "旧一级" in names
    legacy = next(n for n in tree if n["name"] == "旧一级")
    assert legacy["level"] == 1
    assert legacy["children"][0]["name"] == "旧二级"
    assert legacy["children"][0]["level"] == 2
    assert legacy["children"][0]["path"] == "旧一级 / 旧二级"
