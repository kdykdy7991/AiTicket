"""Publish POC analysis and verification fields for constellation tickets."""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.core.database import async_session
from app.models.node_form import FormBinding, FormDefinition, FormFieldDefinition


async def seed_constellation_analysis_form(session_factory=None) -> None:
    async with (session_factory or async_session)() as db:
        form = (await db.execute(select(FormDefinition).where(
            FormDefinition.code == "constellation_analysis_v1",
            FormDefinition.version == 1,
        ))).scalar_one_or_none()
        if form is None:
            form = FormDefinition(code="constellation_analysis_v1", name="提交分析验证",
                                  node_type="analysis", version=1, enabled=True,
                                  published_at=None)
            db.add(form)
            await db.flush()
            reason_labels = {
                "technical": "技术原因", "management": "管理原因",
                "technical_management": "技术与管理原因",
            }
            db.add(FormFieldDefinition(
                form_definition_id=form.id, field_key="reason_category", label="原因分类",
                field_type="select", sort_order=0, required=True,
                options=list(reason_labels), validation={"option_labels": reason_labels},
                storage_type="submission",
            ))
            common = (
                (1, "rectification_completion_at", "整改完成时间", "text"),
                (2, "process_analysis", "问题过程分析", "textarea"),
                (3, "long_term_rectification_measure", "长期整改措施", "textarea"),
                (4, "verification_situation", "验证情况", "textarea"),
            )
            technical = (
                (5, "mechanism_analysis", "机理分析", "textarea"),
                (6, "analysis_report", "举一反三", "textarea"),
                (7, "conclusion", "结论", "textarea"),
            )
            management = (
                (8, "responsible_person", "责任人", "textarea"),
                (9, "rule_improvement", "完善规章制度", "textarea"),
            )
            for fields, condition in (
                (common, None),
                (technical, {"field_in": {"field": "reason_category",
                                          "values": ["technical", "technical_management"]}}),
                (management, {"field_in": {"field": "reason_category",
                                           "values": ["management", "technical_management"]}}),
            ):
                for order, key, label, field_type in fields:
                    db.add(FormFieldDefinition(
                        form_definition_id=form.id, field_key=key, label=label,
                        field_type=field_type, sort_order=order,
                        required=condition is None,
                        visibility_condition=condition, required_condition=condition,
                        validation={"max_length": 40 if field_type == "text" else 4000},
                        storage_type="submission",
                    ))
            db.add(FormFieldDefinition(
                form_definition_id=form.id, field_key="analysis_materials", label="相关材料附件",
                field_type="attachment", sort_order=10, required=False,
                storage_type="system",
            ))
            await db.flush()
            form.published_at = datetime.now(timezone.utc)
        binding = (await db.execute(select(FormBinding).where(
            FormBinding.node_type == "analysis", FormBinding.category_id == 2310,
        ))).scalar_one_or_none()
        if binding is None:
            db.add(FormBinding(node_type="analysis", category_id=2310,
                               category_match_type="descendants_of", form_definition_id=form.id,
                               priority=0, enabled=True))
        await db.commit()


if __name__ == "__main__":
    asyncio.run(seed_constellation_analysis_form())
