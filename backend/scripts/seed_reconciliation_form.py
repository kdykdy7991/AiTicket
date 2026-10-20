"""Published sales handoff form and finance handlers for reconciliation tickets."""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import async_session
from app.core.security import hash_password
from app.models.group import SkillGroup, UserSkillGroup
from app.models.node_form import FormBinding, FormDefinition, FormFieldDefinition
from app.models.user import User


FINANCE_PEOPLE = (("jiangmin", "姜敏"), ("zhujingsheng", "朱景升"))


async def seed_reconciliation_form(session_factory: async_sessionmaker | None = None) -> None:
    async with (session_factory or async_session)() as db:
        finance = (await db.execute(select(SkillGroup).where(SkillGroup.name == "财务"))).scalar_one_or_none()
        if finance is None:
            finance = SkillGroup(name="财务")
            db.add(finance)
            await db.flush()
        for username, name in FINANCE_PEOPLE:
            person = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
            if person is None:
                person = (await db.execute(select(User).where(User.name == name))).scalar_one_or_none()
            if person is None:
                person = User(username=username, name=name, password_hash=hash_password("skdy123"),
                              role="handler", is_active=True)
                db.add(person)
                await db.flush()
            membership = await db.get(UserSkillGroup, (person.id, finance.id))
            if membership is None:
                db.add(UserSkillGroup(user_id=person.id, skill_group_id=finance.id,
                                      is_dispatcher=False))

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
        await db.commit()


if __name__ == "__main__":
    asyncio.run(seed_reconciliation_form())
