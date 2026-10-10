"""V0.21 转派（transfer）：多步链本步完成 → 推进到下一部门。

覆盖设计 §4（链按 steps 顺序推进、快照推进不影响在途配置）：
- open 转派：步骤 +1、部门/对接人切换、owner 清空等下一部门分派；
- Flow Log action_type=transfer（与同边"退回"区分），不置 has_returned；
- 末步/无链/非处理人/非 open 状态拒绝；allowed_actions 下发按钮元数据。
"""

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.category import TicketCategory
from app.models.dispatch import DispatchChain
from app.models.group import SkillGroup, UserSkillGroup
from app.models.ticket import Article, Ticket, TicketStateLog
from app.models.user import User

from test_workflow_regression import _next_phone, action_sequence, as_user

CATS = [
    (2203, None, "套餐变更", 1, 1),
    (2299, None, "平台复核", 1, 2),
]

# 两步链：售后 → 平台运维组（步骤推进的最小可测结构）
STEPS = [
    {"order": 1, "department_code": "售后"},
    {"order": 2, "department_code": "平台运维组"},
]


@pytest_asyncio.fixture
async def tenv(client):
    c, _dispatcher_id, engine = client
    now = datetime.now(timezone.utc)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        existing = set((await s.execute(select(TicketCategory.id))).scalars().all())
        for cid, parent, name, level, sort in CATS:
            if cid not in existing:
                s.add(TicketCategory(
                    id=cid, parent_id=parent, name=name, level=level,
                    sort_order=sort, is_active=True, created_at=now, updated_at=now,
                ))
        sgs = {
            sg.name: sg
            for sg in (await s.execute(
                select(SkillGroup).where(SkillGroup.name.in_(["售后", "平台运维组"]))
            )).scalars()
        }
        sg_aftersale = sgs.get("售后") or SkillGroup(name="售后")
        sg_platform = sgs.get("平台运维组") or SkillGroup(name="平台运维组")
        s.add_all([sg for sg in (sg_aftersale, sg_platform) if sg.id is None])
        await s.flush()
        u_as = User(username="tf-aftersale", name="售后处理人", password_hash="x", role="handler")
        u_pl = User(username="tf-platform", name="平台处理人", password_hash="x", role="handler")
        s.add_all([u_as, u_pl])
        await s.flush()
        s.add_all([
            UserSkillGroup(user_id=u_as.id, skill_group_id=sg_aftersale.id, is_dispatcher=True),
            UserSkillGroup(user_id=u_pl.id, skill_group_id=sg_platform.id, is_dispatcher=True),
        ])
        s.add_all([
            DispatchChain(category_id=2203, steps=STEPS),
            DispatchChain(category_id=2299, steps=[{"order": 1, "department_code": "平台运维组"}]),
        ])
        await s.commit()
        ids = {"aftersale_user": u_as.id, "platform_user": u_pl.id}

    async def create_ticket(**kw):
        payload = dict(
            description="transfer test",
            priority="p3_normal",
            channel="phone",
            customer_type="personal",
            customer_phone=_next_phone(),
            category_id=2203,
        )
        payload.update(kw)
        r = await c.post("/api/v1/tickets", json=payload)
        assert r.status_code == 201, r.text
        return r.json()["data"]

    async def patch(tid, payload, expect=200):
        r = await c.patch(f"/api/v1/tickets/{tid}", json=payload)
        assert r.status_code == expect, r.text
        return r.json() if expect == 200 else r

    async def transfer(tid, expect=200, **body):
        with as_user(ids["aftersale_user"], "handler"):
            r = await c.post(f"/api/v1/tickets/{tid}/articles", data={
                "type": "reply", "body": body.get("reason") or "本部门处理完成",
            })
        assert r.status_code == (201 if expect == 200 else expect), r.text
        return await get(tid) if expect == 200 else r

    async def get(tid):
        r = await c.get(f"/api/v1/tickets/{tid}")
        assert r.status_code == 200, r.text
        return r.json()

    yield {
        "client": c, "engine": engine,
        "create_ticket": create_ticket, "patch": patch, "transfer": transfer,
        "get": get,
        **ids,
    }


async def _open_ticket(tenv, owner_key="aftersale_user"):
    t = await tenv["create_ticket"]()
    t = await tenv["patch"](t["id"], {"state": "open", "owner_id": tenv[owner_key]})
    return t


async def test_transfer_advances_chain(tenv):
    """open → pending：步骤 +1、部门/对接人切到下一步、owner 清空待新部门分派。"""
    t = await _open_ticket(tenv)
    assert t["dispatch_step_index"] == 0

    # allowed_actions 只有 GET/域动作响应会算（PATCH 响应不带）
    detail = await tenv["get"](t["id"])
    actions = {a["action"]: a for a in detail["allowed_actions"]}
    assert "transfer" not in actions, "中间节点只通过处理说明流转"

    d = await tenv["transfer"](t["id"])
    assert d["state"] == "pending"
    assert d["dispatch_step_index"] == 1
    assert d["skill_group_name"] == "平台运维组"
    assert d["dispatcher_id"] == tenv["platform_user"]
    assert d["owner_id"] is None
    # 转派后是 pending：只有分派/撤销/退回，无 transfer
    assert "transfer" not in {a["action"] for a in d["allowed_actions"]}

    assert await action_sequence(tenv, t["id"]) == ["create", "dispatch", "transfer"]
    factory = async_sessionmaker(tenv["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        log = (await s.execute(
            select(TicketStateLog).where(
                TicketStateLog.ticket_id == t["id"],
                TicketStateLog.action_type == "transfer",
            )
        )).scalar_one()
        assert (log.from_state, log.to_state) == ("open", "pending")
        assert "平台运维组" in log.reason          # 默认原因带上落位部门
        assert log.dispatcher_id_snapshot == tenv["platform_user"]
        ticket = (await s.execute(
            select(Ticket).where(Ticket.id == t["id"])
        )).scalar_one()
        assert ticket.has_returned is False, "转派是链前进，不是退回"


async def test_transfer_custom_reason(tenv):
    t = await _open_ticket(tenv)
    d = await tenv["transfer"](t["id"], reason="本步验证完成")
    assert d["state"] == "pending"
    factory = async_sessionmaker(tenv["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        replies = (await s.execute(select(Article).where(Article.ticket_id == t["id"], Article.type == "reply"))).scalars().all()
    assert any(a.body == "本步验证完成" for a in replies)
    async with factory() as s:
        linked_log = await s.get(TicketStateLog, int(replies[0].state_key))
        assert linked_log.to_state == "open"
        assert linked_log.action_type == "dispatch"


async def test_return_after_transfer_restores_previous_department_and_handler(tenv):
    t = await _open_ticket(tenv)
    await tenv["transfer"](t["id"])
    d = await tenv["patch"](t["id"], {"state": "returned", "reason": "需要上一节点补充"})
    assert d["state"] == "open"
    assert d["dispatch_step_index"] == 0
    assert d["skill_group_name"] == "售后"
    assert d["owner_id"] == tenv["aftersale_user"]
    assert d["has_returned"] is True

    d = await tenv["patch"](t["id"], {"state": "pending", "reason": "上一节点也需退回"})
    assert d["state"] == "pending"
    assert d["owner_id"] is None
    assert d["dispatch_step_index"] == 0


async def test_initial_node_returns_to_creator(tenv):
    t = await tenv["create_ticket"]()
    d = await tenv["patch"](t["id"], {"state": "returned", "reason": "请创建人补充信息"})
    assert d["state"] == "returned"
    assert d["owner_id"] == t["creator_id"]
    assert d["returned_to_user_id"] == t["creator_id"]


async def test_resubmit_new_category_rebuilds_route_and_can_resolve(tenv):
    t = await tenv["create_ticket"]()
    await tenv["patch"](t["id"], {"state": "returned", "reason": "分类有误"})
    d = await tenv["patch"](t["id"], {
        "state": "pending", "category_id": 2299,
        "skill_group_id": t["skill_group_id"],
        "dispatcher_id": tenv["aftersale_user"],
    })
    assert d["category_id"] == 2299
    assert d["skill_group_name"] == "平台运维组"
    assert d["dispatcher_id"] == tenv["platform_user"]
    assert d["dispatch_chain_steps"] == [{"order": 1, "department_code": "平台运维组"}]
    assert d["dispatch_step_index"] == 0
    await tenv["patch"](t["id"], {"state": "open", "owner_id": tenv["platform_user"]})
    with as_user(tenv["platform_user"], "handler"):
        result = await tenv["client"].post(
            f"/api/v1/tickets/{t['id']}/articles",
            data={"type": "reply", "body": "重新分类后处理完成"},
        )
    assert result.status_code == 201, result.text
    assert (await tenv["get"](t["id"]))["state"] == "resolved"


async def test_resubmit_same_category_can_reenter_multistep_chain(tenv):
    t = await tenv["create_ticket"]()
    await tenv["patch"](t["id"], {"state": "returned", "reason": "补充后重办"})
    d = await tenv["patch"](t["id"], {"state": "pending", "category_id": 2203})
    assert d["dispatch_step_index"] == 0
    assert d["skill_group_name"] == "售后"
    await tenv["patch"](t["id"], {"state": "open", "owner_id": tenv["aftersale_user"]})
    with as_user(tenv["aftersale_user"], "handler"):
        reply = await tenv["client"].post(
            f"/api/v1/tickets/{t['id']}/articles",
            data={"type": "reply", "body": "售后已处理，交下一部门"},
        )
    assert reply.status_code == 201, reply.text
    d = await tenv["get"](t["id"])
    assert d["state"] == "pending"
    assert d["dispatch_step_index"] == 1
    assert d["skill_group_name"] == "平台运维组"


async def test_transfer_denied_at_last_step(tenv):
    """链末步提交处理说明会办结，不再流转。"""
    t = await _open_ticket(tenv)
    await tenv["transfer"](t["id"])  # 推进到第 2 步（末步）
    await tenv["patch"](t["id"], {"state": "open", "owner_id": tenv["platform_user"]})
    detail = await tenv["get"](t["id"])
    assert "transfer" not in {a["action"] for a in detail["allowed_actions"]}
    with as_user(tenv["platform_user"], "handler"):
        resp = await tenv["client"].post(f"/api/v1/tickets/{t['id']}/articles", data={"type": "reply", "body": "最终处理完成"})
    assert resp.status_code == 201, resp.text
    assert (await tenv["get"](t["id"]))["state"] == "resolved"


async def test_transfer_denied_when_not_owner(tenv):
    """触发人 = 当前处理人自己；非处理人无权转派。"""
    t = await _open_ticket(tenv)
    with as_user(999999, "agent"):
        r = await tenv["client"].post(f"/api/v1/tickets/{t['id']}/articles", data={"type": "reply", "body": "试图代办"})
    assert r.status_code == 403
    assert "当前处理人" in str(r.json())


async def test_transfer_denied_outside_open(tenv):
    """pending（未分派）不可转派。"""
    t = await tenv["create_ticket"]()
    with as_user(tenv["aftersale_user"], "handler"):
        resp = await tenv["client"].post(f"/api/v1/tickets/{t['id']}/articles", data={"type": "reply", "body": "提前处理"})
    assert resp.status_code in (403, 422)


async def test_direct_transfer_and_state_patch_cannot_skip_reply(tenv):
    t = await _open_ticket(tenv)
    direct = await tenv["client"].post(f"/api/v1/tickets/{t['id']}/transfer", json={})
    assert direct.status_code == 404
    patch = await tenv["patch"](t["id"], {"state": "resolved"}, expect=422)
    assert "处理说明" in patch.json()["detail"]
    with as_user(tenv["aftersale_user"], "handler"):
        empty = await tenv["client"].post(f"/api/v1/tickets/{t['id']}/articles", data={"type": "reply", "body": "   "})
    assert empty.status_code == 422


async def test_transfer_then_next_dept_closes(tenv):
    """转派后下一部门可正常分派并处理（链端到端）。"""
    t = await _open_ticket(tenv)
    await tenv["transfer"](t["id"])
    t2 = await tenv["patch"](t["id"], {"state": "open", "owner_id": tenv["platform_user"]})
    assert t2["owner_id"] == tenv["platform_user"]
    assert t2["dispatch_step_index"] == 1
    r = await tenv["patch"](t["id"], {"state": "resolved", "solution": "链末端已处理"})
    assert r["state"] == "resolved"


async def test_reply_advances_intermediate_step_and_only_final_reply_resolves(tenv):
    t = await _open_ticket(tenv)
    detail = await tenv["get"](t["id"])
    assert "resolve" not in {a["action"] for a in detail["allowed_actions"]}

    with as_user(tenv["aftersale_user"], "handler"):
        first = await tenv["client"].post(
            f"/api/v1/tickets/{t['id']}/articles",
            data={"type": "reply", "body": "第一部门审核完成"},
        )
    assert first.status_code == 201, first.text
    t = await tenv["get"](t["id"])
    assert t["state"] == "pending"
    assert t["dispatch_step_index"] == 1
    assert t["skill_group_name"] == "平台运维组"
    assert t["owner_id"] is None
    assert t["solved_at"] is None
    assert await action_sequence(tenv, t["id"]) == ["create", "dispatch", "transfer"]

    await tenv["patch"](t["id"], {"state": "open", "owner_id": tenv["platform_user"]})
    with as_user(tenv["platform_user"], "handler"):
        final = await tenv["client"].post(
            f"/api/v1/tickets/{t['id']}/articles",
            data={"type": "reply", "body": "第二部门执行完成"},
        )
    assert final.status_code == 201, final.text
    t = await tenv["get"](t["id"])
    assert t["state"] == "resolved"
    assert t["solved_at"] is not None
    assert await action_sequence(tenv, t["id"]) == ["create", "dispatch", "transfer", "dispatch", "resolve"]
