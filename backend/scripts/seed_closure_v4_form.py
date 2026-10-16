"""Publish V0.15 closure fields without changing historical closure_v3."""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import async_session
from app.models.node_form import FormBinding, FormDefinition, FormFieldDefinition
from scripts.seed_closure_form import RESULT_LABELS, RESULT_OPTIONS


FORM_CODE = "closure_v4"
CALLBACK_REQUIRED = {"field_equals": {"field": "callback_required", "value": True}}
CALLBACK_DONE = {"field_equals": {"field": "callback_completed", "value": True}}
NOT_RECOGNIZED = {"field_equals": {"field": "customer_recognized", "value": False}}
OTHER_RESULT = {"field_equals": {"field": "closure_result", "value": "other"}}

# key, label, kind, required, options, validation, visibility, required_when,
# storage, storage_key
FIELDS = [
    ("callback_completed", "是否已完成回访", "boolean", True, None, None,
     CALLBACK_REQUIRED, None, "ticket_field", "is_callbacked"),
    ("callback_details", "回访记录", "textarea", False, None, {"max_length": 2000},
     CALLBACK_DONE, None, "ticket_field", "callback_details"),
    ("customer_recognized", "客户对处理结果是否认可", "boolean", True, None,
     {"boolean_labels": {"true": "认可", "false": "不认可"}},
     CALLBACK_DONE, None, "ticket_field", "customer_recognized"),
    ("customer_satisfaction_score", "客户满意度评分", "integer", False, None,
     {"min": 1, "max": 10}, CALLBACK_DONE, None, "ticket_field", "customer_satisfaction_score"),
    ("unsatisfied_reason", "客户不满原因", "textarea", False, None,
     {"max_length": 2000}, NOT_RECOGNIZED, NOT_RECOGNIZED, "ticket_field", "unsatisfied_reason"),
    ("closure_result", "关单结果", "select", True, RESULT_OPTIONS,
     {"option_labels": RESULT_LABELS}, None, None, "ticket_field", "closure_result"),
    ("closure_result_note", "关单结果补充说明", "textarea", False, None,
     {"max_length": 2000}, None, OTHER_RESULT, "submission", None),
    ("archive_notes", "归档说明", "textarea", False, None,
     {"max_length": 2000}, None, None, "ticket_field", "archive_notes"),
]


async def seed_closure_v4_form(session_factory: async_sessionmaker | None = None) -> None:
    async with (session_factory or async_session)() as db:
        form = (await db.execute(select(FormDefinition).where(
            FormDefinition.code == FORM_CODE, FormDefinition.version == 1,
        ))).scalar_one_or_none()
        if form is None:
            form = FormDefinition(code=FORM_CODE, name="客服回访闭环", node_type="closure",
                                  version=1, enabled=True, published_at=None)
            db.add(form)
            await db.flush()
            for order, (key, label, kind, required, options, validation, visible,
                        required_when, storage, storage_key) in enumerate(FIELDS):
                db.add(FormFieldDefinition(
                    form_definition_id=form.id, field_key=key, label=label, field_type=kind,
                    sort_order=order, required=required, options=options, validation=validation,
                    visibility_condition=visible, required_condition=required_when,
                    storage_type=storage, storage_key=storage_key,
                ))
            await db.flush()
            form.published_at = datetime.now(timezone.utc)

        old_ids = (await db.execute(select(FormDefinition.id).where(
            FormDefinition.code.in_(("closure_v1", "closure_v2", "closure_v3"))
        ))).scalars().all()
        if old_ids:
            await db.execute(update(FormBinding).where(
                FormBinding.node_type == "closure", FormBinding.form_definition_id.in_(old_ids)
            ).values(enabled=False))
        binding = (await db.execute(select(FormBinding).where(
            FormBinding.node_type == "closure", FormBinding.form_definition_id == form.id,
            FormBinding.department_code.is_(None), FormBinding.category_id.is_(None),
        ))).scalars().first()
        if binding is None:
            db.add(FormBinding(node_type="closure", department_code=None, category_id=None,
                               category_match_type="exact", form_definition_id=form.id,
                               priority=1, enabled=True))
        else:
            binding.enabled = True
        await db.commit()


if __name__ == "__main__":
    asyncio.run(seed_closure_v4_form())
