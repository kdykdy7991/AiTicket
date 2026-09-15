"""领导角色：全量只读访问。"""

import io


async def test_leader_can_view_all_formal_tickets_and_export(api):
    api.as_("presales01")
    first = (await api.create_ticket(title="售前一的工单")).json()["data"]["id"]
    api.as_("presales02")
    second = (await api.create_ticket(title="售前二的工单")).json()["data"]["id"]

    api.as_("Tony")
    listed = await api.c.get("/api/v1/tickets", params={"page_size": 100})
    assert listed.status_code == 200
    ids = {ticket["id"] for ticket in listed.json()["data"]}
    assert {first, second} <= ids
    assert (await api.detail(first))["allowed_actions"] == []

    exported = await api.c.get("/api/v1/tickets/export")
    assert exported.status_code == 200
    text = exported.content.decode("utf-8-sig")
    assert "售前一的工单" in text and "售前二的工单" in text


async def test_leader_cannot_create_update_act_or_upload(api):
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]

    api.as_("Tony")
    assert (await api.create_ticket()).status_code == 403
    assert (await api.c.patch(
        f"/api/v1/tickets/{ticket_id}", json={"title": "越权修改"}
    )).status_code == 403
    assert (await api.action(ticket_id, "approve", expect=403)).status_code == 403
    upload = await api.c.post(
        f"/api/v1/tickets/{ticket_id}/attachments",
        files={"files": ("proof.txt", io.BytesIO(b"read only"), "text/plain")},
    )
    assert upload.status_code == 403
