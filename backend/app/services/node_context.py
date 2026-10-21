"""Read-only responsibility context derived from current ticket facts.

This module does not mutate Ticket or grant permissions. Domain actions remain
owned by state_machine and the existing ticket/article endpoints.
"""

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket import Ticket
from app.models.user import User
from app.services.dispatch_chain import category_children, judging_department

NodeType = Literal["intake", "assignment", "triage", "processing", "phone_feedback", "closure", "sales_opportunity"]


class NodeContextConflict(ValueError):
    """Persisted workflow facts cannot describe one unambiguous active node."""


@dataclass(frozen=True)
class NodeContext:
    ticket_id: int
    node_type: NodeType | None
    category_id: int | None
    department_id: int | None
    department_code: str | None
    dispatch_step_index: int | None
    dispatch_stage: str | None
    operator_id: int
    owner_id: int | None
    dispatcher_id: int | None
    allowed_actions: list[dict]


async def derive_node_type(db: AsyncSession, ticket: Ticket) -> tuple[NodeType | None, str | None, str | None]:
    """Resolve objective duty, current department name and step stage."""
    steps = ticket.dispatch_chain_steps
    index = ticket.dispatch_step_index
    step = None
    if (steps is None) != (index is None):
        raise NodeContextConflict("分派链与当前步骤不一致")
    if steps is not None:
        if not isinstance(steps, list) or not steps or index < 0 or index >= len(steps):
            raise NodeContextConflict("当前分派步骤超出分派链")
        step = steps[index]
        if not isinstance(step, dict) or not step.get("department_code"):
            raise NodeContextConflict("当前分派步骤缺少部门")

    from app.models.group import SkillGroup
    department = await db.get(SkillGroup, ticket.skill_group_id) if ticket.skill_group_id else None
    department_code = department.name if department else None
    stage = step.get("stage") if step else None
    if stage not in (None, "judgement", "phone_feedback"):
        raise NodeContextConflict(f"未知分派阶段：{stage}")
    if step and department_code != step["department_code"]:
        raise NodeContextConflict("当前责任部门与分派链步骤不一致")

    if ticket.is_draft or ticket.state == "returned":
        node_type: NodeType | None = "intake"
    elif ticket.state in ("archived", "cancelled"):
        node_type = None
    elif ticket.state == "resolved":
        node_type = "closure"
    elif ticket.state in ("pending", "open", "on_hold"):
        if ticket.category_id == 2301 and ticket.state == "pending" and department_code == "售后":
            return "assignment", department_code, stage
        if ticket.is_opportunity:
            if ticket.category_id is not None or stage is not None:
                raise NodeContextConflict("线索工单不应进入分类分派链")
            if department_code != "销售":
                raise NodeContextConflict("线索工单当前责任部门不是销售")
            return "sales_opportunity", department_code, stage
        judgement = await judging_department(db, ticket.category_id)
        children = await category_children(db, ticket.category_id) if ticket.category_id else []
        triage = bool(children and judgement and department_code == judgement)
        if stage == "phone_feedback":
            if triage:
                raise NodeContextConflict("当前步骤同时表示分诊与致电反馈")
            node_type = "phone_feedback"
        else:
            node_type = "triage" if triage else "processing"
    else:
        raise NodeContextConflict(f"未知工单状态：{ticket.state}")
    return node_type, department_code, stage


def node_action_error(node_type: NodeType | None, action: str) -> str | None:
    """Filter candidate domain actions by duty; identity checks remain elsewhere."""
    if node_type == "assignment" and action in {"refine", "reply", "resolve", "hold", "transfer"}:
        return "请先由售后负责人指派售后人员，再进行问题判断"
    if node_type == "triage" and action in {"dispatch", "reply", "resolve", "hold", "transfer"}:
        return "当前节点须先细化问题分类，不能分派或提交处理结果"
    if node_type == "phone_feedback" and action in {"refine", "transfer", "resolve", "hold"}:
        # 致电反馈是链末步：先提交反馈记录，不做与反馈无关的暂缓。
        return "当前节点须提交致电反馈记录"
    if node_type == "sales_opportunity" and action in {"refine", "dispatch", "reply", "transfer", "resolve", "hold"}:
        return "当前节点须提交销售线索处理表单"
    return None


async def resolve_node_context(
    db: AsyncSession,
    ticket: Ticket,
    operator: User,
    *,
    state_actions: list[dict] | None = None,
    article_actions: dict[str, bool] | None = None,
    refine: dict | None = None,
) -> NodeContext:
    """Resolve one node from the current ticket and compose existing permissions.

    ``node_type`` is viewer-independent. An operator lacking permission still
    sees the ticket's actual responsibility node, with no corresponding action.
    Terminal tickets have no active node (``node_type=None``).
    """
    from app.services.state_machine import (
        compute_allowed_actions, compute_article_actions, refine_capability,
    )
    if state_actions is None:
        state_actions = await compute_allowed_actions(db, ticket, operator)
    if article_actions is None:
        article_actions = compute_article_actions(ticket, operator)
    if refine is None:
        refine = await refine_capability(db, ticket, operator)

    index = ticket.dispatch_step_index
    node_type, department_code, stage = await derive_node_type(db, ticket)

    actions = [dict(action) for action in state_actions if node_action_error(node_type, action["action"]) is None]
    if node_type == "triage" and refine.get("can_refine"):
        actions.append({"action": "refine", "target_state": ticket.state, "label": "分诊"})
    for capability, action, label in (
        ("can_reply", "reply", "提交处理说明"),
        ("can_addition", "addition", "追加信息"),
        ("can_remind", "remind", "催办"),
    ):
        if article_actions.get(capability) and node_action_error(node_type, action) is None:
            actions.append({"action": action, "target_state": ticket.state, "label": label})

    return NodeContext(
        ticket_id=ticket.id, node_type=node_type, category_id=ticket.category_id,
        department_id=ticket.skill_group_id, department_code=department_code,
        dispatch_step_index=index, dispatch_stage=stage, operator_id=operator.id,
        owner_id=ticket.owner_id, dispatcher_id=ticket.dispatcher_id,
        allowed_actions=actions,
    )
