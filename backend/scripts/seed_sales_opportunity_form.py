"""Create the sales department, placeholder handler, and published form."""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.security import hash_password
from app.core.database import async_session
from app.models.group import SkillGroup, UserSkillGroup
from app.models.node_form import FormBinding, FormDefinition, FormFieldDefinition
from app.models.user import User


RATING_OPTIONS = ["1", "2", "3", "4", "5"]
PLACEHOLDER_USERNAME = "sales_placeholder"
PLACEHOLDER_NAME = "销售处理人（占位）"


async def seed_sales_opportunity_form(session_factory: async_sessionmaker | None = None) -> None:
    async with (session_factory or async_session)() as db:
        group = (await db.execute(select(SkillGroup).where(SkillGroup.name == "销售"))).scalar_one_or_none()
        if group is None:
            group = SkillGroup(name="销售")
            db.add(group)
            await db.flush()
        placeholder = (await db.execute(select(User).where(
            User.username == PLACEHOLDER_USERNAME,
        ))).scalar_one_or_none()
        if placeholder is None:
            # Same initial password as the other seeded personnel; replace this
            # account with a named salesperson once the actual owner is known.
            placeholder = User(username=PLACEHOLDER_USERNAME, name=PLACEHOLDER_NAME,
                               password_hash=hash_password("skdy123"), role="handler",
                               is_active=True)
            db.add(placeholder)
            await db.flush()
        membership = await db.get(UserSkillGroup, (placeholder.id, group.id))
        if membership is None:
            db.add(UserSkillGroup(user_id=placeholder.id, skill_group_id=group.id,
                                  is_dispatcher=True))
        else:
            membership.is_dispatcher = True
        form = (await db.execute(select(FormDefinition).where(
            FormDefinition.code == "sales_opportunity_v1", FormDefinition.version == 1,
        ))).scalar_one_or_none()
        if form is None:
            form = FormDefinition(code="sales_opportunity_v1", name="销售商机处理",
                                  node_type="sales_opportunity", version=1, enabled=True, published_at=None)
            db.add(form)
            await db.flush()
            fields = (
                ("valid_opportunity", "是否为有效商机", "boolean", None, "submission", None),
                ("customer_rating", "客户评级", "select", RATING_OPTIONS, "submission", None),
                ("sales_opinion", "处理意见", "textarea", None, "article", "body"),
            )
            for order, (key, label, kind, options, storage, storage_key) in enumerate(fields):
                db.add(FormFieldDefinition(form_definition_id=form.id, field_key=key, label=label,
                    field_type=kind, sort_order=order, required=True, options=options,
                    validation={"max_length": 4000} if kind == "textarea" else None,
                    storage_type=storage, storage_key=storage_key))
            db.add(FormBinding(node_type="sales_opportunity", department_code="销售", category_id=None,
                               category_match_type="exact", form_definition_id=form.id,
                               priority=0, enabled=True))
            await db.flush()
            form.published_at = datetime.now(timezone.utc)
        await db.commit()


if __name__ == "__main__":
    asyncio.run(seed_sales_opportunity_form())
