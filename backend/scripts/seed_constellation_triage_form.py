"""Publish the constellation lead's second-level triage form."""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import async_session
from app.models.node_form import FormBinding, FormDefinition, FormFieldDefinition


FORM_CODE = "constellation_triage_v1"
CATEGORY_ID = 2310
DEPARTMENT = "星座大系统负责人"


async def seed_constellation_triage_form(session_factory: async_sessionmaker | None = None) -> None:
    async with (session_factory or async_session)() as db:
        form = (await db.execute(select(FormDefinition).where(
            FormDefinition.code == FORM_CODE, FormDefinition.version == 1,
        ))).scalar_one_or_none()
        if form is None:
            form = FormDefinition(code=FORM_CODE, name="星座大系统分诊", node_type="triage",
                                  version=1, enabled=True, published_at=None)
            db.add(form)
            await db.flush()
            db.add(FormFieldDefinition(
                form_definition_id=form.id, field_key="initial_opinion", label="初步核查意见",
                field_type="textarea", sort_order=0, required=True,
                validation={"max_length": 2000}, storage_type="submission",
            ))
            await db.flush()
            form.published_at = datetime.now(timezone.utc)
        binding = (await db.execute(select(FormBinding).where(
            FormBinding.node_type == "triage",
            FormBinding.department_code == DEPARTMENT,
            FormBinding.category_id == CATEGORY_ID,
        ))).scalar_one_or_none()
        if binding is None:
            db.add(FormBinding(node_type="triage", department_code=DEPARTMENT,
                               category_id=CATEGORY_ID, category_match_type="exact",
                               form_definition_id=form.id, priority=0, enabled=True))
        await db.commit()


if __name__ == "__main__":
    asyncio.run(seed_constellation_triage_form())
