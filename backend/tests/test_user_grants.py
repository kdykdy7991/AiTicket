"""Capability grants are configured through user management, not env vars."""

from app.core.config import settings
from app.core.deps import get_current_user
from app.main import app

READ_DOMAINS = [
    "knowledge_read", "org_read", "reports_read", "tickets_read_all", "visit_read",
]
ALL_GRANTS = READ_DOMAINS + ["assistant_access"]


def _headers(login_response):
    return {"Authorization": "Bearer " + login_response.json()["access_token"]}


def _fake_admin():
    return type(
        "_FakeAdmin", (), {"id": 1, "group_id": None, "role": "admin", "is_active": True}
    )()


async def _create_handler(http, username):
    dept = await http.post("/api/v1/skill-groups", json={"name": "授权测试部门-" + username})
    assert dept.status_code == 201, dept.text
    created = await http.post("/api/v1/users", json={
        "username": username, "name": "待授权处理人",
        "password": "test-password", "role": "handler",
        "skill_groups": [{"skill_group_id": dept.json()["data"]["id"]}],
    })
    assert created.status_code == 201, created.text
    return created.json()["data"]["id"]


async def _login(http, username):
    """Use the real JWT dependency instead of the admin override."""
    app.dependency_overrides.pop(get_current_user, None)
    response = await http.post("/api/v1/auth/login", json={
        "username": username, "password": "test-password",
    })
    assert response.status_code == 200, response.text
    return response


async def _grants_of(http, user_id):
    listed = await http.get("/api/v1/users")
    return next(u for u in listed.json()["data"] if u["id"] == user_id)["grants"]


async def test_grant_configured_in_user_management(client, monkeypatch):
    monkeypatch.setattr(settings, "EXTRA_OBSERVER_USER_IDS", "")
    http, _, _ = client
    target_id = await _create_handler(http, "grant-target")

    granted = await http.patch(f"/api/v1/users/{target_id}", json={"grants": ["reports_read"]})
    assert granted.status_code == 200, granted.text
    assert await _grants_of(http, target_id) == ["reports_read"]

    login = await _login(http, "grant-target")
    assert login.json()["user"]["role"] == "handler"
    assert login.json()["user"]["grants"] == ["reports_read"]
    assert login.json()["user"]["extra_observer_access"] is False
    headers = _headers(login)
    assert (await http.get("/api/v1/stats/report", headers=headers)).status_code == 200
    assert (await http.get("/api/v1/sla-policies", headers=headers)).status_code == 403
    assert (await http.get("/api/v1/tickets", headers=headers)).status_code == 200
    # The grant only widens reads; writes are still governed by the original role.
    assert (await http.patch("/api/v1/users/1", headers=headers, json={"name": "x"})).status_code == 403
    assert (await http.post("/api/v1/tickets", headers=headers, json={})).status_code == 403


async def test_grant_can_be_revoked_and_db_wins_over_env(client, monkeypatch):
    http, _, _ = client
    target_id = await _create_handler(http, "revoke-target")
    monkeypatch.setattr(settings, "EXTRA_OBSERVER_USER_IDS", str(target_id))

    assert (await http.patch(
        f"/api/v1/users/{target_id}", json={"grants": READ_DOMAINS}
    )).status_code == 200
    revoked = await http.patch(f"/api/v1/users/{target_id}", json={"grants": []})
    assert revoked.status_code == 200, revoked.text
    assert await _grants_of(http, target_id) == []

    # Once user management has saved grants, the legacy whitelist no longer
    # resurrects a revoked capability.
    login = await _login(http, "revoke-target")
    assert login.json()["user"]["grants"] == []
    assert login.json()["user"]["extra_observer_access"] is False
    assert (await http.get("/api/v1/stats/report", headers=_headers(login))).status_code == 403


async def test_legacy_env_whitelist_expands_into_read_domains(client, monkeypatch):
    http, _, _ = client
    target_id = await _create_handler(http, "legacy-target")
    monkeypatch.setattr(settings, "EXTRA_OBSERVER_USER_IDS", str(target_id))

    assert await _grants_of(http, target_id) == READ_DOMAINS
    login = await _login(http, "legacy-target")
    assert set(login.json()["user"]["grants"]) == set(READ_DOMAINS)
    assert login.json()["user"]["extra_observer_access"] is True
    for path in ("/api/v1/stats/report", "/api/v1/sla-policies",
                 "/api/v1/visit-records", "/api/v1/knowledge/collections"):
        resp = await http.get(path, headers=_headers(login))
        assert resp.status_code != 403, (path, resp.text)

    # The first save persists the expanded domains, after which the whitelist
    # can be removed without losing access.
    app.dependency_overrides[get_current_user] = _fake_admin
    assert (await http.patch(
        f"/api/v1/users/{target_id}", json={"grants": READ_DOMAINS}
    )).status_code == 200
    monkeypatch.setattr(settings, "EXTRA_OBSERVER_USER_IDS", "")
    assert await _grants_of(http, target_id) == READ_DOMAINS


async def test_unknown_grant_is_rejected(client, monkeypatch):
    monkeypatch.setattr(settings, "EXTRA_OBSERVER_USER_IDS", "")
    http, _, _ = client
    target_id = await _create_handler(http, "unknown-grant")
    assert (await http.patch(
        f"/api/v1/users/{target_id}", json={"grants": ["not_a_grant"]}
    )).status_code == 422
    created = await http.post("/api/v1/users", json={
        "username": "bad-grant", "name": "坏权限", "password": "test-password",
        "role": "observer", "grants": ["not_a_grant"],
    })
    assert created.status_code == 422


async def test_assistant_grant_unlocks_only_its_own_endpoint(client, monkeypatch):
    """Without Debussy config a request that passes auth returns 503; a denied
    one returns 403. This exercises the whole chain without an upstream call."""
    monkeypatch.setattr(settings, "EXTRA_OBSERVER_USER_IDS", "")
    for key in ("AGENT_EMBED_URL", "AGENT_EMBED_API_URL",
                "AGENT_EMBED_CLIENT_ID", "AGENT_EMBED_CLIENT_SECRET"):
        monkeypatch.setattr(settings, key, "")
    http, _, _ = client
    dept = await http.post("/api/v1/skill-groups", json={"name": "助手授权测试部门"})
    dept_id = dept.json()["data"]["id"]

    async def make(username, role, grants):
        payload = {
            "username": username, "name": username, "password": "test-password",
            "role": role, "grants": grants,
        }
        if role == "department_leader":
            payload["skill_groups"] = [{"skill_group_id": dept_id, "complaint_leader": True}]
        elif role != "observer":
            payload["skill_groups"] = [{"skill_group_id": dept_id}]
        created = await http.post("/api/v1/users", json=payload)
        assert created.status_code == 201, (username, created.text)

    cases = [
        ("plain-handler", "handler", [], 403),
        ("read-handler", "handler", ["reports_read"], 403),
        ("assistant-handler", "handler", ["assistant_access"], 503),
        ("assistant-leader", "department_leader", ["assistant_access"], 503),
        ("assistant-observer", "observer", ["assistant_access"], 403),
    ]
    for username, role, grants, _ in cases:
        await make(username, role, grants)

    for username, _, _, expected in cases:
        login = await _login(http, username)
        if username == "assistant-handler":
            assert "assistant_access" in login.json()["user"]["grants"]
        resp = await http.post(
            "/api/v1/agent/embed/code",
            headers={**_headers(login), "Origin": "http://localhost:5173"},
        )
        assert resp.status_code == expected, (username, resp.status_code, resp.text)

    read_login = await _login(http, "read-handler")
    assert (await http.get("/api/v1/stats/report", headers=_headers(read_login))).status_code == 200


async def test_grant_definitions_no_longer_contain_a_bundle(client):
    http, _, _ = client
    resp = await http.get("/api/v1/grant-definitions")
    assert resp.status_code == 200, resp.text
    definitions = {d["key"]: d for d in resp.json()["data"]}
    assert "global_read" not in definitions
    assert set(definitions) == set(ALL_GRANTS)
    assert {d["kind"] for d in definitions.values()} == {"read", "feature"}
    assert definitions["assistant_access"]["kind"] == "feature"
    assert all(d["label"] and d["description"] for d in definitions.values())


async def test_read_domains_are_independently_configurable(client, monkeypatch):
    """One domain grant must not unlock another domain's endpoints."""
    monkeypatch.setattr(settings, "EXTRA_OBSERVER_USER_IDS", "")
    monkeypatch.setattr(settings, "RAG_API_URL", "")
    monkeypatch.setattr(settings, "RAG_SERVICE_TOKEN", "")
    http, _, _ = client
    dept = await http.post("/api/v1/skill-groups", json={"name": "读域测试部门"})
    dept_id = dept.json()["data"]["id"]

    paths = ["/api/v1/stats/report", "/api/v1/sla-policies",
             "/api/v1/visit-records", "/api/v1/knowledge/collections"]
    cases = [
        ("reports-only", ["reports_read"], 0),
        ("visit-only", ["visit_read"], 2),
        ("knowledge-only", ["knowledge_read"], 3),
        ("org-only", ["org_read"], 1),
    ]

    async def make(username, grants):
        created = await http.post("/api/v1/users", json={
            "username": username, "name": username, "password": "test-password",
            "role": "handler", "grants": grants,
            "skill_groups": [{"skill_group_id": dept_id}],
        })
        assert created.status_code == 201, (username, created.text)

    for username, grants, _ in cases:
        await make(username, grants)
    await make("all-domain-user", READ_DOMAINS)

    for username, _, allowed in cases:
        login = await _login(http, username)
        headers = _headers(login)
        for i, path in enumerate(paths):
            resp = await http.get(path, headers=headers)
            if i == allowed:
                # RAG returns 503 when unconfigured; anything but 403 means auth passed.
                assert resp.status_code != 403, (username, path, resp.text)
            else:
                assert resp.status_code == 403, (username, path, resp.text)

    all_login = await _login(http, "all-domain-user")
    for path in paths:
        resp = await http.get(path, headers=_headers(all_login))
        assert resp.status_code != 403, (path, resp.text)


async def test_tickets_read_all_only_widens_ticket_scope(client, monkeypatch):
    from app.models.category import TicketCategory
    from app.models.ticket import Ticket
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    monkeypatch.setattr(settings, "EXTRA_OBSERVER_USER_IDS", "")
    http, _, engine = client
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    dept = await http.post("/api/v1/skill-groups", json={"name": "工单范围测试部门"})
    created = await http.post("/api/v1/users", json={
        "username": "scope-leader", "name": "范围负责人", "password": "test-password",
        "role": "department_leader",
        "skill_groups": [{"skill_group_id": dept.json()["data"]["id"], "complaint_leader": True}],
    })
    assert created.status_code == 201, created.text
    leader_id = created.json()["data"]["id"]
    async with Session() as db:
        if await db.get(TicketCategory, 2102) is None:
            db.add(TicketCategory(id=2102, name="一般投诉", level=1))
            await db.flush()
        db.add(Ticket(number="SCOPE-OWN", creator_id=1, owner_id=leader_id,
                      category_id=2102, customer_phone="13800138000", state="open", is_draft=False))
        db.add(Ticket(number="SCOPE-OTHER", creator_id=1, owner_id=1,
                      category_id=2102, customer_phone="13800138000", state="open", is_draft=False))
        await db.commit()

    before = await http.get("/api/v1/tickets", headers=_headers(await _login(http, "scope-leader")))
    assert before.status_code == 200, before.text
    assert len(before.json()["data"]) == 1

    app.dependency_overrides[get_current_user] = _fake_admin
    granted = await http.patch(f"/api/v1/users/{leader_id}", json={"grants": ["tickets_read_all"]})
    assert granted.status_code == 200, granted.text

    after = await http.get("/api/v1/tickets", headers=_headers(await _login(http, "scope-leader")))
    assert after.status_code == 200, after.text
    assert len(after.json()["data"]) == 2


async def test_all_grants_can_be_selected_and_revoked_together(client, monkeypatch):
    """No mutual exclusion: the six remaining grants coexist."""
    monkeypatch.setattr(settings, "EXTRA_OBSERVER_USER_IDS", "")
    http, _, _ = client
    target_id = await _create_handler(http, "all-grants")

    saved = await http.patch(f"/api/v1/users/{target_id}", json={"grants": ALL_GRANTS})
    assert saved.status_code == 200, saved.text
    assert set(await _grants_of(http, target_id)) == set(ALL_GRANTS)

    login = await _login(http, "all-grants")
    assert set(login.json()["user"]["grants"]) == set(ALL_GRANTS)
    assert (await http.get("/api/v1/stats/report", headers=_headers(login))).status_code == 200

    app.dependency_overrides[get_current_user] = _fake_admin
    assert (await http.patch(f"/api/v1/users/{target_id}", json={"grants": []})).status_code == 200
    assert await _grants_of(http, target_id) == []
    revoked = await _login(http, "all-grants")
    assert (await http.get("/api/v1/stats/report", headers=_headers(revoked))).status_code == 403


async def test_legacy_bundle_row_is_expanded_for_existing_accounts(client, monkeypatch):
    """A stored global_read row from an older release must not lose access."""
    from app.models.grant import UserGrant
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    monkeypatch.setattr(settings, "EXTRA_OBSERVER_USER_IDS", "")
    http, _, engine = client
    target_id = await _create_handler(http, "legacy-row")
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as db:
        db.add(UserGrant(user_id=target_id, grant_key="global_read"))
        await db.commit()

    assert await _grants_of(http, target_id) == READ_DOMAINS
    login = await _login(http, "legacy-row")
    assert set(login.json()["user"]["grants"]) == set(READ_DOMAINS)
    assert (await http.get("/api/v1/stats/report", headers=_headers(login))).status_code == 200
