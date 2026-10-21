"""Publish V0.16 conclusion fields for business and complaint processing nodes.

Existing published forms and submissions stay immutable. These bindings affect
only the named business categories; technical processing keeps processing_v1.
"""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import async_session
from app.models.category import TicketCategory
from app.models.node_form import FormBinding, FormDefinition, FormFieldDefinition


BUSINESS_CODE = "business_opinion_v1"
PACKAGE_V2_CODE = "package_change_execute_v2"
PACKAGE_CODE = "package_change_execute_v3"
BUSINESS_CATEGORIES = (1202, 1203, 1204)
COMPLAINT_ROOT = 2101
PACKAGE_CATEGORY = 2203


async def _ensure_form(db, *, code: str, name: str, version: int, with_attachment: bool):
    form = (await db.execute(select(FormDefinition).where(
        FormDefinition.code == code, FormDefinition.version == version,
    ))).scalar_one_or_none()
    if form is None:
        form = FormDefinition(code=code, name=name, node_type="processing",
                              version=version, enabled=True, published_at=None)
        db.add(form)
        await db.flush()
        db.add(FormFieldDefinition(
            form_definition_id=form.id, field_key="processing_opinion",
            label="处理意见（结论）", field_type="textarea", sort_order=0,
            required=True, validation={"max_length": 4000},
            storage_type="article", storage_key="body",
        ))
        if with_attachment:
            db.add(FormFieldDefinition(
                form_definition_id=form.id, field_key="related_materials",
                label="附件", field_type="attachment", sort_order=1,
                required=False, storage_type="system",
            ))
        await db.flush()
        form.published_at = datetime.now(timezone.utc)
    return form


async def seed_v016_opinion_forms(session_factory: async_sessionmaker | None = None) -> None:
    async with (session_factory or async_session)() as db:
        business = await _ensure_form(db, code=BUSINESS_CODE, name="业务处理结论",
                                      version=1, with_attachment=False)
        await _ensure_form(db, code=PACKAGE_V2_CODE, name="套餐变更执行",
                           version=2, with_attachment=True)
        package = await _ensure_form(db, code=PACKAGE_CODE, name="套餐变更执行",
                                     version=3, with_attachment=False)

        for category_id, match_type in [
            *((category_id, "exact") for category_id in BUSINESS_CATEGORIES),
            (COMPLAINT_ROOT, "descendants_of"),
        ]:
            # Incremental seed can run before optional V2 categories are present.
            if await db.get(TicketCategory, category_id) is None:
                continue
            existing = (await db.execute(select(FormBinding).where(
                FormBinding.node_type == "processing",
                FormBinding.department_code.is_(None),
                FormBinding.category_id == category_id,
            ))).scalars().all()
            if not any(binding.form_definition_id == business.id for binding in existing):
                db.add(FormBinding(
                    node_type="processing", department_code=None,
                    category_id=category_id, category_match_type=match_type,
                    form_definition_id=business.id, priority=0, enabled=True,
                ))
            for binding in existing:
                binding.enabled = binding.form_definition_id == business.id

        existing = (await db.execute(select(FormBinding).where(
            FormBinding.node_type == "processing",
            FormBinding.department_code == "业务支撑组",
            FormBinding.category_id == PACKAGE_CATEGORY,
        ))).scalars().all()
        if not any(binding.form_definition_id == package.id for binding in existing):
            db.add(FormBinding(
                node_type="processing", department_code="业务支撑组",
                category_id=PACKAGE_CATEGORY, category_match_type="exact",
                form_definition_id=package.id, priority=0, enabled=True,
            ))
        for binding in existing:
            binding.enabled = binding.form_definition_id == package.id
        await db.commit()


if __name__ == "__main__":
    asyncio.run(seed_v016_opinion_forms())
