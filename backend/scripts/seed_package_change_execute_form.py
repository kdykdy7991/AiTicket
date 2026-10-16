"""Publish the lightweight package change execution form for 业务支撑组."""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import async_session
from app.models.node_form import FormBinding, FormDefinition, FormFieldDefinition


FORM_CODE = "package_change_execute_v1"
CATEGORY_ID = 2203
DEPARTMENT = "业务支撑组"


async def seed_package_change_execute_form(session_factory: async_sessionmaker | None = None) -> None:
    async with (session_factory or async_session)() as db:
        form = (await db.execute(select(FormDefinition).where(
            FormDefinition.code == FORM_CODE, FormDefinition.version == 1,
        ))).scalar_one_or_none()
        if form is None:
            form = FormDefinition(code=FORM_CODE, name="套餐变更执行", node_type="processing",
                                  version=1, enabled=True, published_at=None)
            db.add(form)
            await db.flush()
            db.add_all([
                FormFieldDefinition(form_definition_id=form.id, field_key="processing_opinion",
                                    label="处理记录", field_type="textarea", sort_order=0,
                                    required=True, storage_type="article", storage_key="body",
                                    validation={"max_length": 4000}),
                FormFieldDefinition(form_definition_id=form.id, field_key="related_materials",
                                    label="附件", field_type="attachment", sort_order=1,
                                    required=False, storage_type="system"),
            ])
        binding = (await db.execute(select(FormBinding).where(
            FormBinding.node_type == "processing",
            FormBinding.department_code == DEPARTMENT,
            FormBinding.category_id == CATEGORY_ID,
        ))).scalar_one_or_none()
        if binding is None:
            db.add(FormBinding(node_type="processing", department_code=DEPARTMENT,
                               category_id=CATEGORY_ID, category_match_type="exact",
                               form_definition_id=form.id, priority=0, enabled=True))
        if form.published_at is None:
            form.published_at = datetime.now(timezone.utc)
        await db.commit()


if __name__ == "__main__":
    asyncio.run(seed_package_change_execute_form())
