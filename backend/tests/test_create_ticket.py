"""回归测试：create_ticket / submit_draft 的人员快照 bug。

覆盖两个已修复的回归：
- AttributeError: 'TicketCreate' object has no attribute 'owner_id'（正式建单）
- NameError: submit_draft 引用了不存在的 body 变量（草稿提交）

注：is_draft 等状态走 DB 层断言——_ticket_to_brief() 漏传 is_draft 字段，
响应里恒为 False，不能信响应（该序列化 bug 另行处理）。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket import Ticket, TicketStateLog
from app.models.category import TicketCategory


async def test_create_formal_ticket_writes_snapshot(client):
    """正式建单 -> 201，且 state_log 快照正确（不再 AttributeError）。"""
    c, dispatcher_id, engine = client
    resp = await c.post(
        "/api/v1/tickets",
        json={
            "customer_phone": "13800000000",
            "dispatcher_id": dispatcher_id,
            "is_draft": False,
        },
    )
    assert resp.status_code == 201, resp.text

    async with AsyncSession(engine) as s:
        log = (
            await s.execute(
                select(TicketStateLog).order_by(TicketStateLog.id.desc()).limit(1)
            )
        ).scalar_one()
        assert log.to_state == "pending"
        assert log.owner_id_snapshot is None  # 建单时无处理人
        assert log.dispatcher_id_snapshot == dispatcher_id


async def test_create_draft(client):
    """草稿建单 -> 201，DB 里 is_draft=True（不再走 _snapshot_people 分支）。"""
    c, _dispatcher_id, engine = client
    resp = await c.post(
        "/api/v1/tickets",
        json={"customer_phone": "13900000000", "is_draft": True},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["is_draft"] is True  # _ticket_to_brief 曾漏传 is_draft

    async with AsyncSession(engine) as s:
        t = (
            await s.execute(select(Ticket).order_by(Ticket.id.desc()).limit(1))
        ).scalar_one()
        assert t.is_draft is True
        assert t.number is None  # 草稿无工单号


async def test_submit_draft(client):
    """草稿提交 -> 200（端点默认状态码），转正式且生成工单号（不再 NameError）。"""
    c, dispatcher_id, engine = client

    # 先建草稿（带 dispatcher_id，提交时必需）
    resp = await c.post(
        "/api/v1/tickets",
        json={
            "customer_phone": "13700000000",
            "dispatcher_id": dispatcher_id,
            "is_draft": True,
        },
    )
    assert resp.status_code == 201, resp.text
    draft_id = resp.json()["data"]["id"]

    # 提交草稿
    resp = await c.post(f"/api/v1/tickets/drafts/{draft_id}/submit")
    assert resp.status_code == 200, resp.text  # submit_draft 未显式设 201

    async with AsyncSession(engine) as s:
        t = (await s.execute(select(Ticket).where(Ticket.id == draft_id))).scalar_one()
        assert t.is_draft is False
        assert t.number is not None  # 提交后才生成工单号

async def test_intake_form_persists_new_fields(client):
    c, dispatcher_id, engine = client
    async with AsyncSession(engine) as s:
        s.add_all([
            TicketCategory(id=2201, name="业务运营", level=1),
            TicketCategory(id=2203, parent_id=2201, name="套餐变更", level=2),
        ])
        await s.commit()
    payload = {
        "intake_form": True, "is_draft": False,
        "customer_type": "enterprise", "customer_name": "王先生",
        "customer_company": "蓝海智联科技有限公司", "industry": "海洋渔业",
        "customer_phone": "13800000000", "contact_phone": "13900000000",
        "customer_email": "contact@example.com", "channel": "web",
        "category_id": 2203, "satellite_number": "8986043100123456789",
        "is_opportunity": False, "expected_result": "远程排查",
        "priority": "p2_high", "description": "套餐变更后无法正常使用。",
        "dispatcher_id": dispatcher_id,
    }
    resp = await c.post('/api/v1/tickets', json=payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()['data']
    assert data['industry'] == '海洋渔业'
    assert data['customer_email'] == 'contact@example.com'
    assert data['satellite_number'] == payload['satellite_number']
    assert data['is_opportunity'] is False
    assert data['expected_result'] == '远程排查'
    assert data['channel'] == 'web'

    async with AsyncSession(engine) as s:
        t = (await s.execute(select(Ticket).where(Ticket.id == data['id']))).scalar_one()
        assert t.industry == '海洋渔业'
        assert t.expected_result == '远程排查'


async def test_intake_form_requires_assurance_fields(client):
    c, dispatcher_id, engine = client
    async with AsyncSession(engine) as s:
        s.add_all([
            TicketCategory(id=2301, name="业务保障", level=1),
            TicketCategory(id=2302, parent_id=2301, name="应用平台", level=2),
        ])
        await s.commit()
    payload = {
        "intake_form": True, "customer_name": "王先生", "customer_company": "蓝海智联",
        "industry": "海洋渔业", "customer_phone": "13800000000",
        "category_id": 2302, "is_opportunity": False,
        "expected_result": "远程排查", "description": "终端离线",
        "dispatcher_id": dispatcher_id,
    }
    resp = await c.post('/api/v1/tickets', json=payload)
    assert resp.status_code == 422
    assert '卫星物联网码号' in resp.json()['detail']
    assert '故障发生时间' in resp.json()['detail']


async def test_intake_form_allows_partial_draft(client):
    c, _dispatcher_id, engine = client
    resp = await c.post('/api/v1/tickets', json={"intake_form": True, "is_draft": True})
    assert resp.status_code == 201, resp.text
    async with AsyncSession(engine) as s:
        t = (await s.execute(select(Ticket).where(Ticket.id == resp.json()['data']['id']))).scalar_one()
        assert t.is_draft is True
        assert t.customer_phone == ''

async def test_intake_assurance_persists_fault_information(client):
    c, dispatcher_id, engine = client
    async with AsyncSession(engine) as s:
        s.add_all([
            TicketCategory(id=2301, name="业务保障", level=1),
            TicketCategory(id=2302, parent_id=2301, name="应用平台", level=2),
        ])
        await s.commit()
    payload = {
        "intake_form": True, "customer_name": "王先生", "customer_company": "蓝海智联",
        "industry": "海洋渔业", "customer_phone": "13800000000",
        "category_id": 2302, "satellite_number": "8986043100123456789",
        "is_opportunity": False, "expected_result": "远程排查", "description": "终端离线",
        "fault_occurred_at": "2026-10-15T09:30:00+08:00",
        "fault_recurrence": "偶发", "fault_location": "28.123456, 122.340987",
        "is_batch_fault": False, "dispatcher_id": dispatcher_id,
    }
    resp = await c.post('/api/v1/tickets', json=payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()['data']
    assert data['fault_recurrence'] == '偶发'
    assert data['fault_location'] == '28.123456, 122.340987'
    assert data['is_batch_fault'] is False
    assert data['fault_occurred_at'] is not None

async def test_intake_draft_can_be_loaded_and_updated(client):
    c, _dispatcher_id, _engine = client
    created = await c.post('/api/v1/tickets', json={"intake_form": True, "is_draft": True})
    assert created.status_code == 201, created.text
    draft_id = created.json()['data']['id']
    updated = await c.patch(f'/api/v1/tickets/drafts/{draft_id}', json={
        "intake_form": True, "is_draft": True, "customer_name": "王先生",
        "industry": "海洋渔业", "customer_email": "contact@example.com",
    })
    assert updated.status_code == 200, updated.text
    loaded = await c.get(f'/api/v1/tickets/{draft_id}')
    assert loaded.status_code == 200, loaded.text
    assert loaded.json()['is_draft'] is True
    assert loaded.json()['industry'] == '海洋渔业'
    assert loaded.json()['customer_email'] == 'contact@example.com'

async def test_intake_complaint_level_follows_selected_category(client):
    c, dispatcher_id, engine = client
    async with AsyncSession(engine) as s:
        s.add_all([
            TicketCategory(id=2101, name="服务投诉", level=1),
            TicketCategory(id=2103, parent_id=2101, name="重要投诉", level=2),
        ])
        await s.commit()
    resp = await c.post('/api/v1/tickets', json={
        "intake_form": True, "customer_name": "王先生", "customer_company": "蓝海智联",
        "industry": "海洋渔业", "customer_phone": "13800000000",
        "category_id": 2103, "is_opportunity": False, "expected_result": "解释说明",
        "description": "投诉服务响应不及时", "dispatcher_id": dispatcher_id,
        "complaint_level": "重大",  # 客户端值不能覆盖分类派生的级别
    })
    assert resp.status_code == 201, resp.text
    assert resp.json()['data']['complaint_level'] == '重要'
