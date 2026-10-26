"""Publish the professional handler's POC response measures form."""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.core.database import async_session
from app.models.node_form import FormBinding, FormDefinition, FormFieldDefinition


async def seed_constellation_response_form(session_factory=None) -> None:
    async with (session_factory or async_session)() as db:
        form = (await db.execute(select(FormDefinition).where(
            FormDefinition.code == "constellation_response_plan_v1",
            FormDefinition.version == 1,
        ))).scalar_one_or_none()
        if form is None:
            form = FormDefinition(code="constellation_response_plan_v1", name="提交响应措施",
                                  node_type="response_plan", version=1, enabled=True,
                                  published_at=None)
            db.add(form)
            await db.flush()
            for order, key, label, required, field_type in (
                (0, "initial_investigation", "初步排查结论", True, "textarea"),
                (1, "temporary_measure", "临时响应措施", True, "textarea"),
                (2, "long_term_measure", "长期措施", False, "textarea"),
                (3, "planned_completion_at", "计划完成时间", False, "text"),
            ):
                db.add(FormFieldDefinition(
                    form_definition_id=form.id, field_key=key, label=label,
                    field_type=field_type, sort_order=order, required=required,
                    validation={"max_length": 4000 if field_type == "textarea" else 40},
                    storage_type="submission",
                ))
            await db.flush()
            form.published_at = datetime.now(timezone.utc)
        binding = (await db.execute(select(FormBinding).where(
            FormBinding.node_type == "response_plan", FormBinding.category_id == 2310,
        ))).scalar_one_or_none()
        if binding is None:
            db.add(FormBinding(node_type="response_plan", category_id=2310,
                               category_match_type="descendants_of", form_definition_id=form.id,
                               priority=0, enabled=True))
        await db.commit()


if __name__ == "__main__":
    asyncio.run(seed_constellation_response_form())
