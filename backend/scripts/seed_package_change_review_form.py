"""Publish the market department's package change review form."""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import async_session
from app.models.node_form import FormBinding, FormDefinition, FormFieldDefinition


FORM_CODE = "package_change_review_v1"
CATEGORY_ID = 2203
DEPARTMENT = "市场生态部"


async def seed_package_change_review_form(session_factory: async_sessionmaker | None = None) -> None:
    async with (session_factory or async_session)() as db:
        form = (await db.execute(select(FormDefinition).where(
            FormDefinition.code == FORM_CODE, FormDefinition.version == 1,
        ))).scalar_one_or_none()
        if form is None:
            form = FormDefinition(code=FORM_CODE, name="套餐变更审核", node_type="processing",
                                  version=1, enabled=True, published_at=None)
            db.add(form)
            await db.flush()
            for order, key, label, kind, required, storage, storage_key in (
                (0, "new_package_name", "新套餐名称", "text", True, "submission", None),
                (1, "change_application", "变更申请单附件", "attachment", False, "system", None),
                (2, "processing_opinion", "处理意见（结论）", "textarea", True, "article", "body"),
            ):
                db.add(FormFieldDefinition(
                    form_definition_id=form.id, field_key=key, label=label, field_type=kind,
                    sort_order=order, required=required, storage_type=storage, storage_key=storage_key,
                    validation={"max_length": 200 if key == "new_package_name" else 4000} if kind != "attachment" else None,
                ))
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
    asyncio.run(seed_package_change_review_form())
