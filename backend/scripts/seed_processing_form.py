"""Idempotent v1 processing form shared by all responsibility departments."""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow `python scripts/seed_processing_form.py` (script dir, not the backend root).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import async_session
from app.models.node_form import FormBinding, FormDefinition, FormFieldDefinition


# A controlled starter vocabulary, versioned with the published form.
CAUSE_OPTIONS = ["软件缺陷", "硬件故障", "配置错误", "网络/环境", "操作问题", "其他"]
LONG_TERM = {"field_equals": {"field": "requires_long_term_action", "value": True}}

FIELDS = [
    ("cause_category", "原因分类", "select", True, CAUSE_OPTIONS, None, "submission", None, 50),
    ("root_cause", "根因分析", "textarea", True, None, None, "ticket_field", "root_cause", 4000),
    ("temporary_measure", "临时处置措施", "textarea", True, None, None, "submission", None, 4000),
    ("requires_long_term_action", "根因无法短期解决", "boolean", True, None, None, "submission", None, None),
    ("long_term_plan", "长期整改方案", "textarea", False, None, LONG_TERM, "submission", None, 4000),
    ("related_materials", "相关材料附件", "attachment", False, None, None, "system", None, None),
    ("processing_opinion", "处理意见（结论）", "textarea", True, None, None, "article", "body", 4000),
]


async def seed_processing_form(session_factory: async_sessionmaker | None = None) -> None:
    async with (session_factory or async_session)() as db:
        existing = (await db.execute(select(FormDefinition).where(
            FormDefinition.code == "processing_v1", FormDefinition.version == 1,
        ))).scalar_one_or_none()
        if existing:
            return
        form = FormDefinition(code="processing_v1", name="责任部门处理", node_type="processing",
                              version=1, enabled=True, published_at=None)
        db.add(form)
        await db.flush()
        for order, (key, label, kind, required, options, condition, storage, storage_key, limit) in enumerate(FIELDS):
            db.add(FormFieldDefinition(
                form_definition_id=form.id, field_key=key, label=label, field_type=kind,
                sort_order=order, required=required, options=options,
                validation={"max_length": limit} if limit else None,
                visibility_condition=condition, required_condition=condition if key == "long_term_plan" else None,
                storage_type=storage, storage_key=storage_key,
            ))
        # One base binding; department-specific overrides can be added later.
        db.add(FormBinding(node_type="processing", department_code=None, category_id=None,
                           category_match_type="exact", form_definition_id=form.id,
                           priority=0, enabled=True))
        await db.flush()
        form.published_at = datetime.now(timezone.utc)
        await db.commit()


if __name__ == "__main__":
    asyncio.run(seed_processing_form())
