"""Package intake choices remove both departmental dispatch steps."""
import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.category import TicketCategory
from app.models.dispatch import DispatchChain
from app.models.group import SkillGroup, UserSkillGroup
from app.models.user import User
from scripts.seed_package_change_review_form import seed_package_change_review_form
from scripts.seed_package_change_execute_form import seed_package_change_execute_form
from test_direct_assign import _setup_direct_assign
from test_workflow_regression import as_user, _next_phone


@pytest.mark.asyncio
@pytest.mark.parametrize('draft', [False, True])
async def test_package_intake_assignments(client, draft):
    http, _, engine = client
    ids = await _setup_direct_assign(engine)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        category = await db.get(TicketCategory, 2203)
        if category is None:
            category = TicketCategory(id=2203, name='套餐变更', level=1, direct_assign=True)
            db.add(category)
        category.direct_assign = True
        support = SkillGroup(name='业务支撑组')
        executor = User(username='package-executor', name='练露', role='handler', password_hash='x')
        db.add_all([support, executor])
        await db.flush()
        executor_id = executor.id
        db.add(UserSkillGroup(user_id=executor_id, skill_group_id=support.id, is_dispatcher=True))
        chain = await db.scalar(select(DispatchChain).where(DispatchChain.category_id == 2203))
        steps = [{'order': 1, 'department_code': '市场生态部'}, {'order': 2, 'department_code': '业务支撑组'}]
        if chain:
            chain.steps = steps
        else:
            db.add(DispatchChain(category_id=2203, steps=steps))
        await db.commit()
    await seed_package_change_review_form(factory)
    await seed_package_change_execute_form(factory)
    with as_user(1, 'agent'):
        routing = await http.post('/api/v1/routing-rules/resolve', json={'category_id': 2203})
        assert routing.status_code == 200, routing.text
        departments = routing.json()['data']['assignment_departments']
        assert len(departments[0]['handlers']) == 3
        assert departments[1]['handlers'] == [{'id': executor_id, 'name': '练露'}]
        payload = {'category_id': 2203, 'customer_phone': _next_phone(), 'description': '变更套餐'}
        missing = await http.post('/api/v1/tickets', json=payload)
        assert missing.status_code == 422, missing.text
        wrong = await http.post('/api/v1/tickets', json={**payload, 'owner_id': ids['outsider']})
        assert wrong.status_code == 422, wrong.text
        payload.update({'is_draft': draft, 'dispatch_owner_ids': {'市场生态部': ids['handler_a']}})
        response = await http.post('/api/v1/tickets', json=payload)
        assert response.status_code == 201, response.text
        ticket = response.json()['data']
        if draft:
            edited = await http.patch(f"/api/v1/tickets/drafts/{ticket['id']}", json=payload)
            assert edited.status_code == 200, edited.text
            detail = await http.get(f"/api/v1/tickets/{ticket['id']}")
            assert detail.status_code == 200, detail.text
            response = await http.post(f"/api/v1/tickets/drafts/{ticket['id']}/submit")
            assert response.status_code == 200, response.text
            ticket = response.json()['data']
    assert ticket['state'] == 'open' and ticket['owner_id'] == ids['handler_a']
    assert [s['assigned_owner_id'] for s in ticket['dispatch_chain_steps']] == [ids['handler_a'], executor_id]
    for owner, values in [(ids['handler_a'], {'new_package_name': '新套餐', 'processing_opinion': '审核通过'}),
                          (executor_id, {'processing_opinion': '执行完成'})]:
        with as_user(owner, 'handler'):
            detail = (await http.get(f"/api/v1/tickets/{ticket['id']}")).json()
            assert all(action['action'] != 'dispatch' for action in detail['allowed_actions'])
            form = detail['current_form']
            request = {'form_definition_id': form['form_definition_id'], 'form_version': form['version'],
                       'expected_category_id': 2203, 'expected_department_id': detail['skill_group_id'],
                       'expected_dispatch_step_index': detail['dispatch_step_index'], 'expected_state': 'open',
                       'values': values}
            if owner == ids['handler_a']:
                async with factory() as db:
                    person = await db.get(User, executor_id)
                    person.is_active = False
                    await db.commit()
                invalid = await http.post(f"/api/v1/tickets/{ticket['id']}/node-submit", data={'payload': json.dumps(request)})
                assert invalid.status_code == 422, invalid.text
                unchanged = (await http.get(f"/api/v1/tickets/{ticket['id']}")).json()
                assert unchanged['state'] == 'open' and unchanged['owner_id'] == owner
                async with factory() as db:
                    person = await db.get(User, executor_id)
                    person.is_active = True
                    await db.commit()
            result = await http.post(f"/api/v1/tickets/{ticket['id']}/node-submit", data={'payload': json.dumps(request)})
            assert result.status_code == 200, result.text
            ticket = result.json()['data']
            assert ticket['state'] == ('open' if owner == ids['handler_a'] else 'resolved')
            assert ticket['owner_id'] == executor_id
