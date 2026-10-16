"""Idempotent published v1 form for the after-sales triage node.

Run after database migrations and base/phase9 category seeds.
"""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow `python scripts/seed_triage_form.py` (script dir, not the backend root).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import async_session
from app.models.node_form import FormBinding, FormDefinition, FormFieldDefinition


FIELDS = [
    ("initial_opinion", "初步核查意见", "textarea", True, None, "submission", None, 2000),
    ("terminal_name", "终端名称", "text", False, [2321, 2322], "submission", None, 200),
    ("device_sn", "终端 SN", "text", False, [2321, 2322], "ticket_field", "device_sn", 100),
    ("iccid", "ICCID", "text", False, [2321, 2322], "submission", None, 100),
    ("imsi", "IMSI", "text", False, [2321, 2322], "submission", None, 100),
    ("firmware_version", "终端固件版本号", "text", False, [2321], "submission", None, 100),
    ("host_software_type", "上位机软件类型", "text", False, [2321], "submission", None, 100),
    ("satellite_selection_rule", "选星规则", "textarea", False, [2310], "submission", None, 2000),
    ("obstruction_assessment", "遮挡判定", "textarea", False, [2310], "submission", None, 2000),
]


async def seed_triage_form(session_factory: async_sessionmaker | None = None) -> None:
    async with (session_factory or async_session)() as db:
        existing = (await db.execute(select(FormDefinition).where(
            FormDefinition.code == "after_sales_triage", FormDefinition.version == 1,
        ))).scalar_one_or_none()
        if existing:
            return  # Published versions are immutable.
        form = FormDefinition(code="after_sales_triage", name="售后分诊", node_type="triage",
                              version=1, enabled=True, published_at=None)
        db.add(form)
        await db.flush()
        for index, (key, label, kind, required, categories, storage, storage_key, limit) in enumerate(FIELDS):
            db.add(FormFieldDefinition(
                form_definition_id=form.id, field_key=key, label=label, field_type=kind,
                sort_order=index, required=required, options=None,
                validation={"max_length": limit},
                visibility_condition={"target_descendants_of_any": categories} if categories else None,
                required_condition=None, storage_type=storage, storage_key=storage_key,
            ))
        db.add(FormBinding(node_type="triage", department_code="售后", category_id=2301,
                           category_match_type="descendants_of", form_definition_id=form.id,
                           priority=0, enabled=True))
        await db.flush()
        form.published_at = datetime.now(timezone.utc)
        await db.commit()


if __name__ == "__main__":
    asyncio.run(seed_triage_form())
