"""Customer-service intake creates independent tickets, regardless of matching history."""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from app.models.ticket import Ticket
from test_direct_assign import _setup_direct_assign
from test_workflow_regression import as_user


@pytest.mark.asyncio
@pytest.mark.parametrize('existing_state', ['pending', 'open', 'resolved', 'on_hold', 'archived'])
async def test_same_phone_and_category_creates_independent_tickets(client, existing_state):
    http, _, engine = client
    await _setup_direct_assign(engine)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    payload = {'intake_form': True, 'is_opportunity': False, 'category_id': 1202,
               'customer_phone': '13800000001', 'customer_name': '同号码来电客户',
               'customer_company': '测试单位', 'industry': '未提供', 'description': '品牌合作咨询'}
    with as_user(1, 'agent'):
        original_response = await http.post('/api/v1/tickets', json=payload)
        assert original_response.status_code == 201, original_response.text
        original = original_response.json()['data']
        async with factory() as db:
            (await db.get(Ticket, original['id'])).state = existing_state
            await db.commit()
        ids, numbers = {original['id']}, {original['number']}
        for _ in range(2):
            response = await http.post('/api/v1/tickets', json=payload)
            assert response.status_code == 201, response.text
            created = response.json()
            assert not (created.get('warnings') or {}).get('duplicate_detected')
            assert not (created.get('warnings') or {}).get('duplicate_tickets')
            assert created['data']['is_duplicate'] is False
            ids.add(created['data']['id']); numbers.add(created['data']['number'])
        assert len(ids) == len(numbers) == 3
    async with factory() as db:
        stored = await db.get(Ticket, original['id'])
        assert stored.state == existing_state and stored.number == original['number']
        assert stored.customer_phone == payload['customer_phone'] and stored.category_id == 1202
        assert not stored.is_duplicate


@pytest.mark.asyncio
async def test_matching_draft_can_submit_without_duplicate_warning(client):
    http, _, engine = client
    await _setup_direct_assign(engine)
    payload = {'category_id': 1202, 'customer_phone': '13800000001', 'description': '品牌合作咨询'}
    with as_user(1, 'agent'):
        existing = await http.post('/api/v1/tickets', json=payload)
        assert existing.status_code == 201, existing.text
        draft = await http.post('/api/v1/tickets', json={**payload, 'is_draft': True})
        assert draft.status_code == 201, draft.text
        submitted = await http.post(f"/api/v1/tickets/drafts/{draft.json()['data']['id']}/submit")
        assert submitted.status_code == 200, submitted.text
        assert submitted.json()['data']['id'] != existing.json()['data']['id']
        assert not (submitted.json().get('warnings') or {}).get('duplicate_detected')
