"""Idempotent published v1 form for the after-sales triage node.

Run after database migrations and base/phase9 category seeds.
"""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow `python scripts/seed_triage_form.py` (script dir, not the backend root).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import async_session
from app.models.node_form import FormBinding, FormDefinition, FormFieldDefinition


FIELDS = [
    ("initial_opinion", "初步核查意见", "textarea", True, None, "submission", None, 2000),
    ("terminal_name", "终端名称", "text", False, [2321, 2322], "submission", None, 200),
    ("device_sn", "终端 SN", "text", False, [2321, 2322], "ticket_field", "device_sn", 100),
    ("iccid", "ICCID", "text", False, [2321, 2322], "submission", None, 100),
    ("imsi", "IMSI", "text", False, [2321, 2322], "submission", None, 100),
    ("firmware_version", "终端固件版本号", "text", False, [2321], "submission", None, 100),
    ("host_software_type", "上位机软件类型", "text", False, [2321], "submission", None, 100),
    ("satellite_selection_rule", "选星规则", "textarea", False, [2310], "submission", None, 2000),
    ("obstruction_assessment", "遮挡判定", "textarea", False, [2310], "submission", None, 2000),
]

CONSTELLATION_FIELDS_V2 = [
    ("title", "问题名称", "text", 500, None),
    ("proposer", "提出人", "text", 100, None),
    ("proposer_department", "提出部门", "text", 100, None),
    ("investigation_notes", "初步排查说明", "textarea", 1000, None),
    ("test_scenario", "测试场景", "select", 50, ["客户测", "自测"]),
    ("closure_requirement", "闭环要求", "textarea", 4000, None),
    ("test_device", "测试设备", "text", 2000, None),
    ("terminal_firmware_version", "终端固件版本号", "text", 200, None),
    ("terminal_configuration", "终端配置", "textarea", 4000, None),
    ("host_software", "上位机软件", "text", 300, None),
    ("data_frequency_packet_length", "数据频次及数据包长度", "textarea", 4000, None),
    ("deployment_environment", "部署位置环境状态", "textarea", 4000, None),
]
CONSTELLATION_FIELDS_V3 = [field for field in CONSTELLATION_FIELDS_V2 if field[0] != "title"]


async def seed_triage_form(session_factory: async_sessionmaker | None = None) -> None:
    async with (session_factory or async_session)() as db:
        existing = (await db.execute(select(FormDefinition).where(
            FormDefinition.code == "after_sales_triage", FormDefinition.version == 1,
        ))).scalar_one_or_none()
        if existing:
            return  # Published versions are immutable.
        form = FormDefinition(code="after_sales_triage", name="初步判断依据", node_type="triage",
                              version=1, enabled=True, published_at=None)
        db.add(form)
        await db.flush()
        for index, (key, label, kind, required, categories, storage, storage_key, limit) in enumerate(FIELDS):
            db.add(FormFieldDefinition(
                form_definition_id=form.id, field_key=key, label=label, field_type=kind,
                sort_order=index, required=required, options=None,
                validation={"max_length": limit},
                visibility_condition={"target_descendants_of_any": categories} if categories else None,
                required_condition=None, storage_type=storage, storage_key=storage_key,
            ))
        db.add(FormBinding(node_type="triage", department_code="售后", category_id=2301,
                           category_match_type="descendants_of", form_definition_id=form.id,
                           priority=0, enabled=True))
        await db.flush()
        form.published_at = datetime.now(timezone.utc)
        await db.commit()


async def seed_constellation_intake_fields(session_factory: async_sessionmaker | None = None) -> None:
    """Retain the originally published v2 definition for historical compatibility."""
    await _seed_constellation_intake_version(2, CONSTELLATION_FIELDS_V2, session_factory)


async def seed_constellation_intake_fields_v3(session_factory: async_sessionmaker | None = None) -> None:
    """Publish v3: reuse the ticket's existing title; require the other 12 fields."""
    await _seed_constellation_intake_version(3, CONSTELLATION_FIELDS_V3, session_factory)


async def _seed_constellation_intake_version(
    version: int, fields: list[tuple], session_factory: async_sessionmaker | None = None,
) -> None:
    async with (session_factory or async_session)() as db:
        form = (await db.execute(select(FormDefinition).where(
            FormDefinition.code == "after_sales_triage", FormDefinition.version == version,
        ))).scalar_one_or_none()
        if form is None:
            form = FormDefinition(code="after_sales_triage", name="初步判断依据", node_type="triage",
                                  version=version, enabled=True, published_at=None)
            db.add(form)
            await db.flush()
            star = {"target_descendants_of_any": [2310]}
            non_star = {"target_descendants_of_any": [2302, 2321, 2322]}
            for index, (key, label, kind, required, categories, storage, storage_key, limit) in enumerate(FIELDS):
                is_star_field = key == "satellite_selection_rule"
                db.add(FormFieldDefinition(
                    form_definition_id=form.id, field_key=key, label=label, field_type=kind,
                    sort_order=index, required=False,
                    validation={"max_length": limit},
                    visibility_condition={"target_descendants_of_any": categories} if categories else None,
                    required_condition=star if is_star_field else non_star if key == "initial_opinion" else None,
                    storage_type=storage, storage_key=storage_key,
                ))
            for offset, (key, label, kind, limit, options) in enumerate(fields, start=len(FIELDS)):
                db.add(FormFieldDefinition(
                    form_definition_id=form.id, field_key=key, label=label, field_type=kind,
                    sort_order=offset, required=False, options=options,
                    validation={"max_length": limit},
                    visibility_condition=star, required_condition=star,
                    storage_type="ticket_field" if key == "title" else "submission",
                    storage_key="title" if key == "title" else None,
                ))
            await db.flush()
            form.published_at = datetime.now(timezone.utc)
        bindings = (await db.execute(select(FormBinding).where(
            FormBinding.node_type == "triage", FormBinding.department_code == "售后",
            FormBinding.category_id == 2301,
        ))).scalars().all()
        if not any(binding.form_definition_id == form.id for binding in bindings):
            db.add(FormBinding(node_type="triage", department_code="售后", category_id=2301,
                               category_match_type="descendants_of", form_definition_id=form.id,
                               priority=0, enabled=True))
        for binding in bindings:
            binding.enabled = binding.form_definition_id == form.id
        await db.commit()


if __name__ == "__main__":
    asyncio.run(seed_triage_form())
