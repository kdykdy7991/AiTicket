import json
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.security import create_access_token
from app.main import app
from app.models.category import TicketCategory
from app.models.dispatch import DispatchChain
from app.models.group import SkillGroup, UserSkillGroup
from app.models.user import User
from test_workflow_regression import as_user
from test_processing_form import install_form, request


@pytest.mark.asyncio
@pytest.mark.parametrize('category_id,category_name,group_name,role,responsibility', [
    (2102, '一般投诉', '客户服务组', 'department_leader', '客户服务组负责人'),
    (2103, '重要投诉', '产品', 'department_leader', '产品中心重要投诉'),
    (2104, '重大投诉', '时空道宇', 'division_leader', '部门负责人分管领导'),
])
@pytest.mark.parametrize('draft', [False, True])
async def test_complaint_leader_creation_and_access(client, category_id, category_name, group_name, role, responsibility, draft):
    http, _, engine = client
    form_id = await install_form({'engine': engine})
    async with AsyncSession(engine, expire_on_commit=False) as db:
        root = await db.get(TicketCategory, 2101)
        if not root:
            db.add(TicketCategory(id=2101, name='投诉', level=1))
        category = await db.get(TicketCategory, category_id)
        if not category:
            db.add(TicketCategory(id=category_id, parent_id=2101, name=category_name, level=2))
        group = SkillGroup(name=group_name)
        leader = User(username='test-leader', name='负责人', role=role, password_hash='x')
        db.add_all([group, leader])
        await db.flush()
        group_id, leader_id = group.id, leader.id
        db.add(UserSkillGroup(user_id=leader_id, skill_group_id=group_id, is_dispatcher=False,
                              complaint_leader=category_id != 2104,
                              complaint_division_leader=category_id == 2104,
                              complaint_responsibilities=[responsibility]))
        if not await db.get(DispatchChain, category_id):
            db.add(DispatchChain(category_id=category_id, steps=[{'order': 1, 'department_code': group_name}]))
        await db.commit()
    payload = {'intake_form': True, 'is_opportunity': False, 'category_id': category_id,
               'customer_phone': '13800000001', 'customer_name': '客户', 'customer_company': '单位',
               'industry': '未提供', 'description': '投诉内容', 'skill_group_id': group_id,
               'owner_id': leader_id, 'complaint_responsibility': responsibility, 'is_draft': draft}
    with as_user(1, 'agent'):
        response = await http.post('/api/v1/tickets', json=payload)
        assert response.status_code == 201, response.text
        ticket = response.json()['data']
        if draft:
            response = await http.post(f"/api/v1/tickets/drafts/{ticket['id']}/submit")
            assert response.status_code == 200, response.text
            ticket = response.json()['data']
    assert ticket['state'] == 'open' and ticket['owner_id'] == leader_id

    # Exercise the real authentication dependency, including the restricted leader scope.
    original = app.dependency_overrides.pop(get_current_user)
    try:
        headers = {'Authorization': f'Bearer {create_access_token(leader_id, role)}'}
        own = await http.get(f"/api/v1/tickets/{ticket['id']}", headers=headers)
        assert own.status_code == 200, own.text
        assert any(action['action'] == 'return' for action in own.json()['allowed_actions'])
        listing = await http.get('/api/v1/tickets', headers=headers)
        assert listing.status_code == 200 and ticket['id'] in [row['id'] for row in listing.json()['data']]
        assert (await http.get('/api/v1/users', headers=headers)).status_code == 403
        assert (await http.get('/api/v1/tickets/999999', headers=headers)).status_code == 403
        assert (await http.patch(f"/api/v1/tickets/{ticket['id']}", headers=headers,
                                 json={'priority': 'p1_urgent'})).status_code == 403
        returned = await http.patch(f"/api/v1/tickets/{ticket['id']}", headers=headers,
                                    json={'state': 'pending', 'reason': '请补充信息'})
        assert returned.status_code == 200, returned.text
    finally:
        app.dependency_overrides[get_current_user] = original
    async with AsyncSession(engine) as db:
        leader = await db.get(User, leader_id)
        leader.is_active = False
        await db.commit()
    with as_user(1, 'agent'):
        invalid = await http.patch(f"/api/v1/tickets/{ticket['id']}", json={'state': 'open', 'owner_id': leader_id})
        assert invalid.status_code == 422, invalid.text
    async with AsyncSession(engine) as db:
        leader = await db.get(User, leader_id)
        leader.is_active = True
        await db.commit()
    with as_user(1, 'agent'):
        reassigned = await http.patch(f"/api/v1/tickets/{ticket['id']}", json={'state': 'open', 'owner_id': leader_id})
        assert reassigned.status_code == 200, reassigned.text
    original = app.dependency_overrides.pop(get_current_user)
    try:
        headers = {'Authorization': f'Bearer {create_access_token(leader_id, role)}'}
        data = request(reassigned.json(), form_id)
        completed = await http.post(f"/api/v1/tickets/{ticket['id']}/node-submit", headers=headers,
                                    data={'payload': json.dumps(data)})
        assert completed.status_code == 200, completed.text
        assert completed.json()['data']['state'] == 'resolved'
    finally:
        app.dependency_overrides[get_current_user] = original
