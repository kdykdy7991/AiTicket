"""Route business assurance handling results to after-sales phone feedback.

Revision ID: u5x8y9z0a1b2
Revises: t4w7x8y9z0a1
"""

import json
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = "u5x8y9z0a1b2"
down_revision: Union[str, Sequence[str], None] = "t4w7x8y9z0a1"
branch_labels = None
depends_on = None


HANDLING_DEPARTMENT = {
    2302: "平台运维组",
    2311: "软件开发组",
    2312: "测运控组",
    2313: "整星产品",
    2321: "终端研发",
    2322: "售后",
}


def _feedback_step(order: int) -> dict:
    return {"order": order, "department_code": "售后", "stage": "phone_feedback"}


def _extend_snapshot(category_id: int | None, steps: list | None) -> list | None:
    if category_id not in HANDLING_DEPARTMENT or not steps:
        return steps
    if steps[-1].get("stage") == "phone_feedback":
        return steps
    if steps[-1].get("department_code") != HANDLING_DEPARTMENT[category_id]:
        return steps
    return [*steps, _feedback_step(len(steps) + 1)]


def upgrade() -> None:
    db = op.get_bind()
    for category_id, department in HANDLING_DEPARTMENT.items():
        # Hardware fault starts with the after-sales judgement step. Refinement
        # skips it, leaving separate handling and feedback steps in that team.
        departments = ["售后", "售后", "售后"] if category_id == 2322 else [department, "售后"]
        steps = [
            _feedback_step(index + 1) if index == len(departments) - 1
            else {"order": index + 1, "department_code": name, "stage": "judgement"}
            if category_id == 2322 and index == 0
            else {"order": index + 1, "department_code": name}
            for index, name in enumerate(departments)
        ]
        db.execute(
            text("UPDATE dispatch_chains SET steps = CAST(:steps AS json), updated_at = now() WHERE category_id = :category_id"),
            {"steps": json.dumps(steps, ensure_ascii=False), "category_id": category_id},
        )

    # Tickets keep a chain snapshot. Extend only live handling routes; resolved
    # tickets have already reached the customer-service closeout stage.
    rows = db.execute(text("""
        SELECT id, category_id, dispatch_chain_steps, return_checkpoints
        FROM tickets
        WHERE state IN ('pending', 'open', 'on_hold')
          AND category_id IN (2302, 2311, 2312, 2313, 2321, 2322)
        FOR UPDATE
    """))
    for ticket_id, category_id, steps, checkpoints in rows:
        updated_steps = _extend_snapshot(category_id, steps)
        updated_checkpoints = []
        for checkpoint in checkpoints or []:
            updated = dict(checkpoint)
            updated["dispatch_chain_steps"] = _extend_snapshot(
                updated.get("category_id"), updated.get("dispatch_chain_steps")
            )
            updated_checkpoints.append(updated)
        if updated_steps != steps or updated_checkpoints != (checkpoints or []):
            db.execute(text("""
                UPDATE tickets
                SET dispatch_chain_steps = CAST(:steps AS json),
                    return_checkpoints = CAST(:checkpoints AS json)
                WHERE id = :ticket_id
            """), {
                "steps": json.dumps(updated_steps, ensure_ascii=False),
                "checkpoints": json.dumps(updated_checkpoints, ensure_ascii=False),
                "ticket_id": ticket_id,
            })


def downgrade() -> None:
    # Leave existing ticket snapshots untouched: removing a live step would
    # silently skip work already assigned to after-sales.
    db = op.get_bind()
    for category_id, department in HANDLING_DEPARTMENT.items():
        steps = [{"order": 1, "department_code": department}]
        db.execute(
            text("UPDATE dispatch_chains SET steps = CAST(:steps AS json), updated_at = now() WHERE category_id = :category_id"),
            {"steps": json.dumps(steps, ensure_ascii=False), "category_id": category_id},
        )
