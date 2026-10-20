"""V0.16 business and complaint conclusions use the intended minimal form."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.node_form import FormBinding, FormDefinition
from app.models.ticket import Ticket
from app.services.node_form import resolve_form, validate_submission
from scripts.seed_package_change_execute_form import seed_package_change_execute_form
from scripts.seed_processing_form import seed_processing_form
from scripts.seed_v016_opinion_forms import seed_v016_opinion_forms
from test_v2_categories import _reseed_v2


@pytest.mark.asyncio
async def test_v016_opinion_bindings_requiredness_and_idempotence(client):
    _, _, engine = client
    await _reseed_v2(engine)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await seed_processing_form(factory)
    await seed_package_change_execute_form(factory)
    await seed_v016_opinion_forms(factory)
    await seed_v016_opinion_forms(factory)

    async with factory() as db:
        for category_id, department in [
            (1202, "品牌传播与大客户"), (1203, "产品"),
            (1204, "市场生态部"), (2102, "值班组"),
            (2103, "服务投诉协调组"), (2104, "服务投诉协调组"),
        ]:
            form = await resolve_form(db, SimpleNamespace(
                node_type="processing", category_id=category_id, department_code=department,
            ))
            assert form.definition.code == "business_opinion_v1"
            assert [(field.field_key, field.label, field.required) for field in form.fields] == [
                ("processing_opinion", "处理意见（结论）", True),
            ]
            with pytest.raises(HTTPException) as missing:
                await validate_submission(db, form, Ticket(), None, {})
            assert missing.value.status_code == 422
            data, updates, article, _ = await validate_submission(
                db, form, Ticket(), None, {"processing_opinion": "已处理并告知客户"},
            )
            assert data == updates == {}
            assert article == {"body": "已处理并告知客户"}

        package = await resolve_form(db, SimpleNamespace(
            node_type="processing", category_id=2203, department_code="业务支撑组",
        ))
        assert package.definition.code == "package_change_execute_v2"
        assert package.definition.version == 2
        assert [(field.field_key, field.label, field.required) for field in package.fields] == [
            ("processing_opinion", "处理意见（结论）", True), ("related_materials", "附件", False),
        ]
        assert len((await db.execute(select(FormBinding).where(
            FormBinding.node_type == "processing", FormBinding.enabled.is_(True),
            FormBinding.category_id == 2203, FormBinding.department_code == "业务支撑组",
        ))).scalars().all()) == 1
        old = (await db.execute(select(FormDefinition).where(
            FormDefinition.code == "package_change_execute_v1",
        ))).scalar_one()
        assert old.published_at is not None

        technical = await resolve_form(db, SimpleNamespace(
            node_type="processing", category_id=2321, department_code="终端研发",
        ))
        assert technical.definition.code == "processing_v1"
