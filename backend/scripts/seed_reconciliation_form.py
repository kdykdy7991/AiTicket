"""业财对账经管审核及财务处理表单；保留旧销售表单以读取存量工单。"""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import async_session
from app.models.node_form import FormBinding, FormDefinition, FormFieldDefinition


async def seed_reconciliation_form(session_factory: async_sessionmaker | None = None) -> None:
    async with (session_factory or async_session)() as db:
        review = (await db.execute(select(FormDefinition).where(
            FormDefinition.code == "reconciliation_review_v1", FormDefinition.version == 1,
        ))).scalar_one_or_none()
        if review is None:
            review = FormDefinition(code="reconciliation_review_v1", name="经管审核",
                                    node_type="processing", version=1, enabled=True)
            db.add(review)
            await db.flush()
            db.add(FormFieldDefinition(
                form_definition_id=review.id, field_key="processing_opinion",
                label="处理意见", field_type="textarea", sort_order=0, required=True,
                validation={"max_length": 4000}, storage_type="article", storage_key="body",
            ))
            await db.flush()
            review.published_at = datetime.now(timezone.utc)
        review_binding = (await db.execute(select(FormBinding).where(
            FormBinding.node_type == "processing", FormBinding.department_code == "经营管理部",
            FormBinding.category_id == 2204, FormBinding.form_definition_id == review.id,
        ))).scalar_one_or_none()
        if review_binding is None:
            db.add(FormBinding(node_type="processing", department_code="经营管理部", category_id=2204,
                               category_match_type="exact", form_definition_id=review.id,
                               priority=0, enabled=True))

        form = (await db.execute(select(FormDefinition).where(
            FormDefinition.code == "reconciliation_sales_v1", FormDefinition.version == 1,
        ))).scalar_one_or_none()
        if form is None:
            form = FormDefinition(code="reconciliation_sales_v1", name="业财对账销售提交",
                                  node_type="processing", version=1, enabled=True, published_at=None)
            db.add(form)
            await db.flush()
            fields = (
                ("reconciliation_customer_name", "客户名称", "text", True, None, "submission", None),
                ("project_order_number", "项目订单号", "text", False, None, "submission", None),
                ("finance_company", "财务所属公司", "select", True, ["时空道宇", "青岛上合"], "submission", None),
                ("finance_person", "财务人员", "select", True, ["姜敏", "朱景升"], "submission", None),
                ("related_materials", "相关材料附件", "attachment", False, None, "system", None),
                ("processing_opinion", "提交信息", "textarea", True, None, "article", "body"),
            )
            for order, (key, label, kind, required, options, storage, storage_key) in enumerate(fields):
                db.add(FormFieldDefinition(form_definition_id=form.id, field_key=key, label=label,
                    field_type=kind, sort_order=order, required=required, options=options,
                    validation={"max_length": 4000 if kind == "textarea" else 200},
                    storage_type=storage, storage_key=storage_key))
            db.add(FormBinding(node_type="processing", department_code="销售", category_id=2204,
                               category_match_type="exact", form_definition_id=form.id,
                               priority=0, enabled=True))
            await db.flush()
            form.published_at = datetime.now(timezone.utc)

        finance_form = (await db.execute(select(FormDefinition).where(
            FormDefinition.code == "reconciliation_finance_v1", FormDefinition.version == 1,
        ))).scalar_one_or_none()
        if finance_form is None:
            finance_form = FormDefinition(code="reconciliation_finance_v1", name="业财对账财务处理",
                                          node_type="processing", version=1, enabled=True, published_at=None)
            db.add(finance_form)
            await db.flush()
            db.add(FormFieldDefinition(
                form_definition_id=finance_form.id, field_key="processing_opinion",
                label="处理意见", field_type="textarea", sort_order=0, required=True,
                validation={"max_length": 4000}, storage_type="article", storage_key="body",
            ))
            await db.flush()
            finance_form.published_at = datetime.now(timezone.utc)
        finance_binding = (await db.execute(select(FormBinding).where(
            FormBinding.node_type == "processing", FormBinding.department_code == "财务",
            FormBinding.category_id == 2204, FormBinding.form_definition_id == finance_form.id,
        ))).scalar_one_or_none()
        if finance_binding is None:
            db.add(FormBinding(node_type="processing", department_code="财务", category_id=2204,
                               category_match_type="exact", form_definition_id=finance_form.id,
                               priority=0, enabled=True))
        await db.commit()


if __name__ == "__main__":
    asyncio.run(seed_reconciliation_form())
