"""Fail the deployment when a node that must have a form has no usable definition/binding.

Why this exists: a missing form is not loud. ``resolve_form()`` returns ``None``, the
node form silently stops being enforced and every node falls back to the legacy
``reply`` / transition path. Nothing raises at runtime, so the only safe place to
catch it is right after migration + seed, before the service goes live.

Scope: only the node types listed in ``REQUIRED_NODE_FORMS`` are checked. Having no
form at all is legitimate business configuration for other nodes, so this script does
NOT treat ``resolve_form() is None`` as a global error.

Usage:
    python scripts/check_node_forms.py
Exit code 0 when every required node is configured, 1 otherwise.
"""

import asyncio
import os
import sys
from pathlib import Path

# Allow `python scripts/check_node_forms.py` (script dir, not the backend root).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.models.category import TicketCategory  # noqa: E402
from app.models.node_form import FormBinding, FormDefinition  # noqa: E402

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://skdy:skdy123@localhost:5433/skdy_ticket"
)

# Nodes whose dynamic form is part of the current delivery scope.
REQUIRED_NODE_FORMS: tuple[str, ...] = ("triage", "processing", "phone_feedback", "closure", "sales_opportunity")
REQUIRED_EXACT_BINDINGS = (
    ("constellation_triage_v1", "triage", "星座大系统负责人", 2310),
)


async def check_node_forms(session_factory: async_sessionmaker | None = None) -> list[str]:
    """Return one human-readable problem per unconfigured required node (empty = OK)."""
    engine = None
    if session_factory is None:
        engine = create_async_engine(DATABASE_URL, future=True)
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    problems: list[str] = []
    try:
        async with session_factory() as db:
            for node_type in REQUIRED_NODE_FORMS:
                definitions = (await db.execute(
                    select(FormDefinition).where(
                        FormDefinition.node_type == node_type,
                        FormDefinition.enabled.is_(True),
                        FormDefinition.published_at.is_not(None),
                    )
                )).scalars().all()
                published_ids = {definition.id for definition in definitions}
                if not published_ids:
                    problems.append(
                        f"节点 {node_type}: 没有启用且已发布的 FormDefinition"
                        "（请运行 python scripts/update_seed_data.py）"
                    )
                    continue
                bindings = (await db.execute(
                    select(FormBinding).where(
                        FormBinding.node_type == node_type,
                        FormBinding.enabled.is_(True),
                        FormBinding.form_definition_id.in_(published_ids),
                    )
                )).scalars().all()
                if not bindings:
                    problems.append(
                        f"节点 {node_type}: FormDefinition 已发布但没有启用中的 FormBinding，"
                        "该节点不会解析到任何表单"
                    )
                    continue
                # A binding pointing at a missing/inactive category can never match,
                # which degrades silently just like a missing binding.
                for binding in bindings:
                    if binding.category_id is None:
                        continue
                    category = await db.get(TicketCategory, binding.category_id)
                    if category is None:
                        problems.append(
                            f"节点 {node_type}: FormBinding {binding.id} 绑定的分类 "
                            f"{binding.category_id} 不存在"
                        )
                    elif not category.is_active:
                        problems.append(
                            f"节点 {node_type}: FormBinding {binding.id} 绑定的分类 "
                            f"{binding.category_id}（{category.name}）已停用"
                        )
            for code, node_type, department, category_id in REQUIRED_EXACT_BINDINGS:
                form = (await db.execute(select(FormDefinition).where(
                    FormDefinition.code == code, FormDefinition.enabled.is_(True),
                    FormDefinition.published_at.is_not(None),
                ))).scalar_one_or_none()
                if form is None:
                    problems.append(f"缺少已发布表单 {code}")
                    continue
                binding = (await db.execute(select(FormBinding).where(
                    FormBinding.form_definition_id == form.id,
                    FormBinding.node_type == node_type,
                    FormBinding.department_code == department,
                    FormBinding.category_id == category_id,
                    FormBinding.category_match_type == "exact",
                    FormBinding.enabled.is_(True),
                ))).scalar_one_or_none()
                if binding is None:
                    problems.append(f"表单 {code} 缺少 {department}/{category_id} 的启用精确绑定")
    finally:
        if engine is not None:
            await engine.dispose()
    return problems


async def main() -> int:
    problems = await check_node_forms()
    if not problems:
        print("[Node Forms] OK: " + "、".join(REQUIRED_NODE_FORMS) + " 均已配置已发布表单与绑定。")
        return 0
    print("[Node Forms] FAILED — 动态表单未配置，节点会静默退回旧 reply/流转路径，禁止上线：", file=sys.stderr)
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
