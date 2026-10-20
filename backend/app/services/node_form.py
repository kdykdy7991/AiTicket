"""Read published form bindings and validate the first (triage) submission.

Only bounded JSON predicates are supported. The server owns visibility,
requiredness and storage mapping; clients only submit field values.
"""

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.category import TicketCategory
from app.models.node_form import FormBinding, FormDefinition, FormFieldDefinition
from app.models.ticket import Ticket
from app.services.node_context import NodeContext


@dataclass(frozen=True)
class ResolvedForm:
    definition: FormDefinition
    fields: list[FormFieldDefinition]


def allows_process_note(form: ResolvedForm) -> bool:
    """Conclusion-only forms already provide the node's reply entry."""
    return form.definition.code not in {"business_opinion_v1", "package_change_execute_v2"}


# Ticket columns a published form may write. Explicit whitelist: a form definition
# is configuration, so it may only touch columns the backend already owns.
# - device_sn / root_cause: triage + processing
# - is_callbacked / callback_details / satisfaction / unsatisfied_reason /
#   closure_result / customer_recognized / archive_notes: closure
WRITABLE_TICKET_FIELDS = frozenset({
    "device_sn",
    "root_cause",
    "is_callbacked",
    "callback_details",
    "satisfaction",
    "customer_satisfaction_score",
    "unsatisfied_reason",
    "closure_result",
    "customer_recognized",
    "archive_notes",
})

FORM_NODE_TYPES = ("triage", "processing", "phone_feedback", "closure", "sales_opportunity")


async def _ancestors(db: AsyncSession, category_id: int | None) -> list[int]:
    result: list[int] = []
    seen: set[int] = set()
    while category_id is not None:
        if category_id in seen:
            raise HTTPException(409, detail="分类树存在循环")
        seen.add(category_id)
        result.append(category_id)
        category = await db.get(TicketCategory, category_id)
        if category is None:
            raise HTTPException(409, detail="工单分类不存在")
        category_id = category.parent_id
    return result


async def resolve_form(db: AsyncSession, context: NodeContext) -> ResolvedForm | None:
    """Specificity: department/exact > department/nearest ancestor > department > node.

    The same category rules without a department rank below matching department
    rules but above node only. Equal rank and priority is a configuration error.
    """
    if context.node_type not in FORM_NODE_TYPES:
        return None
    ancestors = await _ancestors(db, context.category_id)
    bindings = (await db.execute(
        select(FormBinding)
        .join(FormDefinition, FormBinding.form_definition_id == FormDefinition.id)
        .options(selectinload(FormBinding.form))
        .where(FormBinding.node_type == context.node_type, FormBinding.enabled.is_(True),
               FormDefinition.enabled.is_(True), FormDefinition.published_at.is_not(None))
    )).scalars().all()
    matches: list[tuple[tuple[int, int, int], FormBinding]] = []
    for binding in bindings:
        if binding.department_code and binding.department_code != context.department_code:
            continue
        if binding.category_id is None:
            category_rank = 0
        elif binding.category_id in ancestors:
            distance = ancestors.index(binding.category_id)
            if binding.category_match_type == "exact" and distance != 0:
                continue
            if binding.category_match_type not in ("exact", "descendants_of"):
                raise HTTPException(409, detail="表单分类匹配类型配置错误")
            category_rank = 1000 - distance
        else:
            continue
        # A department binding always outranks a generic category binding.
        rank = (1 if binding.department_code else 0, category_rank, binding.priority)
        matches.append((rank, binding))
    if not matches:
        return None
    best = max(rank for rank, _ in matches)
    winners = [binding for rank, binding in matches if rank == best]
    if len(winners) != 1:
        raise HTTPException(409, detail={"code": "form_binding_conflict", "message": "同优先级表单绑定冲突"})
    form = winners[0].form
    fields = (await db.execute(
        select(FormFieldDefinition).where(FormFieldDefinition.form_definition_id == form.id)
        .order_by(FormFieldDefinition.sort_order, FormFieldDefinition.id)
    )).scalars().all()
    return ResolvedForm(form, list(fields))


async def _condition(
    db: AsyncSession, condition: dict | None, target_category_id: int | None,
    values: dict | None = None,
) -> bool:
    if not condition:
        return True
    if set(condition) == {"target_descendants_of_any"}:
        roots = condition["target_descendants_of_any"]
        if not isinstance(roots, list) or not all(isinstance(v, int) for v in roots):
            raise HTTPException(409, detail="表单条件配置错误")
        return bool(target_category_id and set(roots).intersection(await _ancestors(db, target_category_id)))
    if set(condition) == {"field_equals"}:
        spec = condition["field_equals"]
        if not isinstance(spec, dict) or set(spec) != {"field", "value"} or not isinstance(spec["field"], str):
            raise HTTPException(409, detail="表单条件配置错误")
        return (values or {}).get(spec["field"]) == spec["value"]
    raise HTTPException(409, detail="不支持的表单条件配置")


async def present_form(
    db: AsyncSession, form: ResolvedForm, ticket: Ticket,
    target_category_id: int | None = None,
    values: dict | None = None,
) -> dict:
    fields = []
    for field in form.fields:
        visible = await _condition(db, field.visibility_condition, target_category_id, values)
        conditional_required = await _condition(db, field.required_condition, target_category_id, values) if field.required_condition else False
        value = getattr(ticket, field.storage_key, None) if field.storage_type == "ticket_field" else None
        fields.append({
            "field_key": field.field_key, "label": field.label, "field_type": field.field_type,
            "sort_order": field.sort_order, "required": visible and (field.required or conditional_required),
            "visible": visible, "options": field.options or [], "value": value,
            "option_labels": (field.validation or {}).get("option_labels", {}),
            "boolean_labels": (field.validation or {}).get("boolean_labels", {}),
            "min": (field.validation or {}).get("min"),
            "max": (field.validation or {}).get("max"),
            "visibility_condition": field.visibility_condition,
            "required_condition": field.required_condition,
        })
    return {"code": form.definition.code, "name": form.definition.name,
            "form_definition_id": form.definition.id, "version": form.definition.version,
            "fields": fields}


async def validate_submission(
    db: AsyncSession, form: ResolvedForm, ticket: Ticket,
    target_category_id: int | None, values: dict[str, Any],
    *, context: dict | None = None,
) -> tuple[dict, dict, dict, list]:
    """校验一次提交并按字段归属分流。

    ``context`` 是由工单既有事实提供的条件求值上下文（例如 closure 的
    ``callback_required``），只参与 visibility / required 判断，不作为可提交字段，
    也不会被客户端伪造。
    """
    if not isinstance(values, dict):
        raise HTTPException(422, detail="表单值必须是对象")
    keys = {field.field_key for field in form.fields}
    if unknown := set(values) - keys:
        raise HTTPException(422, detail=f"未知表单字段：{', '.join(sorted(unknown))}")
    conditions = {**(context or {}), **values}
    submission_data: dict = {}
    ticket_updates: dict = {}
    article_values: dict = {}
    snapshot: list = []
    for field in form.fields:
        visible = await _condition(db, field.visibility_condition, target_category_id, conditions)
        required = field.required or (await _condition(db, field.required_condition, target_category_id, conditions) if field.required_condition else False)
        value = values.get(field.field_key)
        if not visible:
            if field.field_key in values:
                raise HTTPException(422, detail=f"当前分类不允许填写：{field.label}")
            continue
        if required and (value is None or (isinstance(value, str) and not value.strip())):
            raise HTTPException(422, detail=f"{field.label}必填")
        snapshot.append({"key": field.field_key, "label": field.label,
                         "type": field.field_type, "required": required,
                         "options": field.options or [], "validation": field.validation or {},
                         "storage_type": field.storage_type,
                         "storage_key": field.storage_key,
                         # Historical evidence only; Ticket remains the current authority.
                         "submitted_value": value if field.storage_type == "ticket_field" else None})
        if value is None:
            continue
        if field.field_type in ("text", "textarea", "select"):
            if not isinstance(value, str):
                raise HTTPException(422, detail=f"{field.label}类型错误")
            max_length = (field.validation or {}).get("max_length", 2000)
            if len(value) > max_length:
                raise HTTPException(422, detail=f"{field.label}长度超限")
            if field.field_type == "select" and value not in (field.options or []):
                raise HTTPException(422, detail=f"{field.label}选项无效")
        elif field.field_type == "boolean":
            if not isinstance(value, bool):
                raise HTTPException(422, detail=f"{field.label}类型错误")
        elif field.field_type == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                raise HTTPException(422, detail=f"{field.label}必须是整数")
            minimum = (field.validation or {}).get("min")
            maximum = (field.validation or {}).get("max")
            if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
                raise HTTPException(422, detail=f"{field.label}超出允许范围")
        elif field.field_type == "attachment" and field.storage_type == "system":
            raise HTTPException(422, detail=f"{field.label}须通过附件上传")
        else:
            raise HTTPException(409, detail=f"暂不支持字段类型：{field.field_type}")
        if field.storage_type == "submission":
            submission_data[field.storage_key or field.field_key] = value
        elif field.storage_type == "ticket_field" and field.storage_key in WRITABLE_TICKET_FIELDS:
            ticket_updates[field.storage_key] = value
        elif field.storage_type == "article" and field.storage_key == "body":
            article_values["body"] = value
        else:
            raise HTTPException(409, detail=f"不支持的表单存储映射：{field.field_key}")
    return submission_data, ticket_updates, article_values, snapshot
