"""Immediate consultations are not recorded as tickets."""
from __future__ import annotations

import pytest

from e2e_tests.tests import helpers


@pytest.mark.usefixtures("e2e_client", "token", "batch_id")
def test_instant_consultation(e2e_client, token, batch_id):
    assert helpers.find_category_by_name(e2e_client, token, "套餐查询") is None
    payload = helpers.base_ticket_payload(
        customer_name=f"E2E-即时咨询-{batch_id}",
        description=f"[E2E][{batch_id}] 即时答复",
        is_instant_resolve=True,
    )
    response = e2e_client.post(
        f"{helpers.API_BASE}/api/v1/tickets",
        headers=helpers.auth_headers(token),
        json=payload,
    )
    assert response.status_code == 422, response.text
