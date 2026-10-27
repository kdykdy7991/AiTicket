"""回归测试：直指派分类（建单时直接指派处理人，免部门对接人分派）。

规则来源：app/services/direct_assign.py —— 分类表 direct_assign 布尔列，
语义为「自身或任一祖先为 True」。

覆盖：
- 直指派分类建单 → 工单直接进入「处理中」，Flow Log 记 direct_assign（不是分派）
- 直指派分类建单未指定处理人 → 422
- 处理人不属于责任部门 → 422
- 处理人打回 → 回到「待受理、无处理人」，建单人重新指派后可再进入「处理中」
- 非直指派分类不受影响：建单后仍是「待受理」，走部门对接人分派
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import TicketCategory
from app.models.dispatch import DispatchChain
from app.models.group import SkillGroup, UserSkillGroup
from app.models.ticket import Ticket, TicketStateLog
from app.models.user import User


async def _setup_direct_assign(engine) -> dict:
    """预置分类/部门/人员/分派链，返回关键 id。

    测试库在每个用例后被 TRUNCATE，而迁移种子里已有部分分类/部门，
    因此这里一律「有则改、无则建」，两种初始状态都能跑。
    """
    async with AsyncSession(engine) as s:
        async def ensure_group(name: str) -> SkillGroup:
            row = (await s.execute(select(SkillGroup).where(SkillGroup.name == name))).scalar_one_or_none()
            if row is None:
                row = SkillGroup(name=name)
                s.add(row)
                await s.flush()
            return row

        async def ensure_user(username: str, name: str) -> User:
            row = (await s.execute(select(User).where(User.username == username))).scalar_one_or_none()
            if row is None:
                row = User(username=username, name=name, password_hash="x", role="handler")
                s.add(row)
                await s.flush()
            return row

        async def ensure_category(cid: int, parent_id: int | None, name: str, direct_assign: bool) -> None:
            row = (await s.execute(
                select(TicketCategory).where(TicketCategory.id == cid)
            )).scalar_one_or_none()
            if row is None:
                s.add(TicketCategory(id=cid, parent_id=parent_id, name=name, level=2 if parent_id else 1,
                                     direct_assign=direct_assign))
                await s.flush()
            else:
                row.direct_assign = direct_assign

        async def ensure_chain(cid: int, dept: str) -> None:
            row = (await s.execute(
                select(DispatchChain).where(DispatchChain.category_id == cid)
            )).scalar_one_or_none()
            steps = [{"order": 1, "department_code": dept}]
            if row is None:
                s.add(DispatchChain(category_id=cid, steps=steps))
            else:
                row.steps = steps
                row.enabled = True

        market = await ensure_group("市场生态部")
        brand = await ensure_group("品牌传播与大客户")
        dispatcher = await ensure_user("xz", "谢志鹏")
        handler_a = await ensure_user("xt", "徐挺")
        handler_b = await ensure_user("wy", "王颜")
        outsider = await ensure_user("wt", "网运成员")
        brand_dispatcher = await ensure_user("zmq", "钟梦茜")

        s.add_all([
            UserSkillGroup(user_id=dispatcher.id, skill_group_id=market.id, is_dispatcher=True),
            UserSkillGroup(user_id=handler_a.id, skill_group_id=market.id, is_dispatcher=False),
            UserSkillGroup(user_id=handler_b.id, skill_group_id=market.id, is_dispatcher=False),
            UserSkillGroup(user_id=outsider.id, skill_group_id=brand.id, is_dispatcher=False),
            UserSkillGroup(user_id=brand_dispatcher.id, skill_group_id=brand.id, is_dispatcher=True),
        ])
        await ensure_category(1001, None, "客户咨询", False)
        await ensure_category(1204, 1001, "渠道/代理合作", True)
        await ensure_category(1202, 1001, "品牌合作", False)
        await ensure_chain(1204, "市场生态部")
        await ensure_chain(1202, "品牌传播与大客户")
        # 先取 id 再提交：本测试用的 session 默认 expire_on_commit=True，
        # 提交后访问对象属性会触发同步 IO。
        ids = {
            "dispatcher": dispatcher.id,
            "handler_a": handler_a.id,
            "handler_b": handler_b.id,
            "outsider": outsider.id,
        }
        await s.commit()
        return ids


async def _logs(engine, ticket_id: int) -> list[TicketStateLog]:
    async with AsyncSession(engine) as s:
        return list((await s.execute(
            select(TicketStateLog).where(TicketStateLog.ticket_id == ticket_id)
            .order_by(TicketStateLog.id)
        )).scalars().all())


async def test_direct_assign_ticket_starts_in_processing(client):
    """直指派分类建单 → 直接「处理中」，处理人 = 客服指定的人。"""
    c, _dispatcher_id, engine = client
    ids = await _setup_direct_assign(engine)

    resp = await c.post("/api/v1/tickets", json={
        "customer_phone": "13800001111",
        "description": "渠道代理合作咨询",
        "category_id": 1204,
        "owner_id": ids["handler_a"],
        "is_draft": False,
    })
    assert resp.status_code == 201, resp.text

    async with AsyncSession(engine) as s:
        t = (await s.execute(select(Ticket).order_by(Ticket.id.desc()).limit(1))).scalar_one()
        assert t.state == "open", "直指派工单建单即进入处理中"
        assert t.owner_id == ids["handler_a"]
        assert t.first_owner_id == ids["handler_a"]
        assert t.category_id == 1204

    logs = await _logs(engine, t.id)
    assert [log.action_type for log in logs] == ["create", "direct_assign"]
    # 建单即指派不是「分派」——Flow Log 上要能区分开
    assert not any(log.action_type == "dispatch" for log in logs)


async def test_direct_assign_requires_owner(client):
    """直指派分类建单未选处理人 → 422。"""
    c, _dispatcher_id, engine = client
    await _setup_direct_assign(engine)

    resp = await c.post("/api/v1/tickets", json={
        "customer_phone": "13800002222",
        "description": "渠道代理合作咨询",
        "category_id": 1204,
        "is_draft": False,
    })
    assert resp.status_code == 422
    assert "处理人" in resp.json()["detail"]


async def test_direct_assign_owner_must_belong_to_department(client):
    """处理人不属于责任部门 → 422（后端兜底，不靠前端过滤）。"""
    c, _dispatcher_id, engine = client
    ids = await _setup_direct_assign(engine)

    resp = await c.post("/api/v1/tickets", json={
        "customer_phone": "13800003333",
        "description": "渠道代理合作咨询",
        "category_id": 1204,
        "owner_id": ids["outsider"],
        "is_draft": False,
    })
    assert resp.status_code == 422
    assert "责任部门" in resp.json()["detail"]


async def test_direct_assign_return_then_reassign(client):
    """处理人打回 → 回到「待受理、无处理人」；建单人重新指派 → 再进「处理中」。"""
    c, _dispatcher_id, engine = client
    ids = await _setup_direct_assign(engine)

    resp = await c.post("/api/v1/tickets", json={
        "customer_phone": "13800004444",
        "description": "渠道代理合作咨询",
        "category_id": 1204,
        "owner_id": ids["handler_a"],
        "is_draft": False,
    })
    assert resp.status_code == 201, resp.text
    ticket_id = resp.json()["data"]["id"]

    # 处理人打回（open → pending）
    resp = await c.patch(f"/api/v1/tickets/{ticket_id}", json={
        "state": "pending", "reason": "需求不明确，需补充材料",
    })
    assert resp.status_code == 200, resp.text

    async with AsyncSession(engine) as s:
        t = (await s.execute(select(Ticket).where(Ticket.id == ticket_id))).scalar_one()
        assert t.state == "pending"
        assert t.owner_id is None, "打回后待受理工单不应保留处理人"

    # 建单人（客服）重新指派
    resp = await c.patch(f"/api/v1/tickets/{ticket_id}", json={
        "state": "open", "owner_id": ids["handler_b"],
    })
    assert resp.status_code == 200, resp.text

    async with AsyncSession(engine) as s:
        t = (await s.execute(select(Ticket).where(Ticket.id == ticket_id))).scalar_one()
        assert t.state == "open"
        assert t.owner_id == ids["handler_b"]


async def test_non_direct_assign_category_unchanged(client):
    """非直指派分类不受影响：建单后仍是「待受理」，等对接人分派。"""
    c, _dispatcher_id, engine = client
    ids = await _setup_direct_assign(engine)

    resp = await c.post("/api/v1/tickets", json={
        "customer_phone": "13800005555",
        "description": "品牌合作咨询",
        "category_id": 1202,
        "is_draft": False,
    })
    assert resp.status_code == 201, resp.text

    async with AsyncSession(engine) as s:
        t = (await s.execute(select(Ticket).order_by(Ticket.id.desc()).limit(1))).scalar_one()
        assert t.state == "pending", "非直指派分类仍走对接人分派"
        assert t.owner_id is None

    logs = await _logs(engine, t.id)
    assert [log.action_type for log in logs] == ["create"]


async def test_direct_assign_draft_submit(client):
    """直指派草稿提交 → 直接进入「处理中」。"""
    c, _dispatcher_id, engine = client
    ids = await _setup_direct_assign(engine)

    resp = await c.post("/api/v1/tickets", json={
        "customer_phone": "13800006666",
        "description": "渠道代理合作咨询",
        "category_id": 1204,
        "owner_id": ids["handler_a"],
        "is_draft": True,
    })
    assert resp.status_code == 201, resp.text
    draft_id = resp.json()["data"]["id"]

    resp = await c.post(f"/api/v1/tickets/drafts/{draft_id}/submit")
    assert resp.status_code == 200, resp.text

    async with AsyncSession(engine) as s:
        t = (await s.execute(select(Ticket).where(Ticket.id == draft_id))).scalar_one()
        assert t.is_draft is False
        assert t.state == "open"
        assert t.owner_id == ids["handler_a"]
