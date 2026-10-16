"""Publish phone feedback v2 while retaining the immutable v1 definition."""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow `python scripts/seed_phone_feedback_form.py` (script dir, not the backend root).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import async_session
from app.models.node_form import FormBinding, FormDefinition, FormFieldDefinition


VERIFICATION_OPTIONS = ["passed", "failed", "partial", "unable"]
VERIFICATION_LABELS = {"passed": "验证通过", "failed": "验证未通过", "partial": "部分恢复", "unable": "无法验证"}
V1_FIELDS = [
    ("verification_status", "验证状态", "select", "submission", None, VERIFICATION_OPTIONS),
    ("verification_conclusion", "验证结论", "textarea", "submission", None, None),
    ("phone_feedback_result", "致电反馈结果", "textarea", "article", "body", None),
]
FIELDS = [("phone_feedback_result", "致电反馈结果", "textarea", "article", "body", None)]


async def seed_phone_feedback_form(session_factory: async_sessionmaker | None = None) -> None:
    async with (session_factory or async_session)() as db:
        existing = (await db.execute(select(FormDefinition).where(
            FormDefinition.code == "phone_feedback_v1", FormDefinition.version == 1,
        ))).scalar_one_or_none()
        if existing is None:
            existing = FormDefinition(code="phone_feedback_v1", name="售后致电反馈", node_type="phone_feedback",
                                      version=1, enabled=True, published_at=None)
            db.add(existing)
            await db.flush()
            for order, (key, label, kind, storage, storage_key, options) in enumerate(V1_FIELDS):
                db.add(FormFieldDefinition(
                    form_definition_id=existing.id, field_key=key, label=label, field_type=kind,
                    sort_order=order, required=True, options=options,
                    validation={"max_length": 4000} if kind == "textarea" else {"option_labels": VERIFICATION_LABELS},
                    storage_type=storage, storage_key=storage_key,
                ))
            await db.flush()
            existing.published_at = datetime.now(timezone.utc)

        v2 = (await db.execute(select(FormDefinition).where(
            FormDefinition.code == "phone_feedback_v2", FormDefinition.version == 2,
        ))).scalar_one_or_none()
        if v2 is None:
            v2 = FormDefinition(code="phone_feedback_v2", name="售后致电反馈", node_type="phone_feedback",
                                version=2, enabled=True, published_at=None)
            db.add(v2)
            await db.flush()
            db.add(FormFieldDefinition(
                form_definition_id=v2.id, field_key="phone_feedback_result", label="致电反馈结果",
                field_type="textarea", sort_order=0, required=True, validation={"max_length": 4000},
                storage_type="article", storage_key="body",
            ))
            await db.flush()
            v2.published_at = datetime.now(timezone.utc)

        bindings = (await db.execute(select(FormBinding).where(
            FormBinding.node_type == "phone_feedback",
            FormBinding.department_code.is_(None), FormBinding.category_id.is_(None),
        ))).scalars().all()
        if not any(binding.form_definition_id == v2.id for binding in bindings):
            db.add(FormBinding(node_type="phone_feedback", department_code=None, category_id=None,
                               category_match_type="exact", form_definition_id=v2.id,
                               priority=0, enabled=True))
        for binding in bindings:
            binding.enabled = binding.form_definition_id == v2.id
        await db.commit()


if __name__ == "__main__":
    asyncio.run(seed_phone_feedback_form())
