"""派单引擎：dispatch_chains（表A 链）读取与部门人员（表B）处方。

设计：docs/ticket_dispatch_design.md §3 / §4。
- resolve_chain：分类 → 唯一链；分类自身无链时沿父链上溯（与旧
  resolve_rule 同继承语义）——子分类有自己的链时先精确命中，不会误继承。
- prescribe_dept：部门代称 → (skill_group, dispatcher, owner) 处方。
  成员排序对接人优先：单人部门即"对接人=处理人"（V0.21 对接人列），
  多人部门由对接人在分派时指定，此处给出默认处方。
- resolve_responsibility：建单/预填统一入口——链优先，无链回退旧
  category_routing_rules（双轨过渡，设计 §8.3 第 5 步清理前保留）。
"""

from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import TicketCategory
from app.models.dispatch import DispatchChain
from app.models.group import SkillGroup, UserSkillGroup
from app.models.user import User

async def resolve_chain(db: AsyncSession, category_id: int | None) -> dict | None:
    """分类 → 启用中的链。返回 {"matched_category_id", "steps"}；无链返回 None。"""
    if category_id is None:
        return None
    cat_id: int | None = category_id
    visited: set[int] = set()
    while cat_id is not None and cat_id not in visited:
        visited.add(cat_id)
        row = (
            await db.execute(
                select(DispatchChain).where(
                    DispatchChain.category_id == cat_id,
                    DispatchChain.enabled == True,  # noqa: E712
                )
            )
        ).scalar_one_or_none()
        if row is not None:
            return {"matched_category_id": cat_id, "steps": row.steps or []}
        parent = await db.execute(
            select(TicketCategory.parent_id).where(TicketCategory.id == cat_id)
        )
        cat_id = parent.scalar_one_or_none()
    return None


async def get_dept(db: AsyncSession, department_code: str) -> SkillGroup | None:
    """部门代称 → skill_group（表 A steps 的 department_code 与 skill_groups.name 对齐）。"""
    result = await db.execute(
        select(SkillGroup).where(SkillGroup.name == department_code)
    )
    return result.scalar_one_or_none()


async def prescribe_dept(db: AsyncSession, department_code: str) -> dict | None:
    """部门代称 → 建单/转派处方。

    返回 {"skill_group_id", "dispatcher_id", "owner_id"}：
    - dispatcher_id：该部门对接人（is_dispatcher=true，取生效中第一人）；
    - owner_id：默认处理人 = 对接人优先（单人部门两者同人）；
    - 部门不存在返回 None；部门无人时 id 全为 None（调用方降级为人工指定）。
    生效区间（effective_from/to）过滤：NULL=当前生效（向后兼容存量行）。
    """
    sg = await get_dept(db, department_code)
    if sg is None:
        return None
    now = datetime.now(timezone.utc)
    rows = (
        await db.execute(
            select(UserSkillGroup, User)
            .join(User, User.id == UserSkillGroup.user_id)
            .where(
                UserSkillGroup.skill_group_id == sg.id,
                User.is_active == True,  # noqa: E712
                or_(
                    UserSkillGroup.effective_from.is_(None),
                    UserSkillGroup.effective_from <= now,
                ),
                or_(
                    UserSkillGroup.effective_to.is_(None),
                    UserSkillGroup.effective_to >= now,
                ),
            )
            .order_by(UserSkillGroup.is_dispatcher.desc(), UserSkillGroup.user_id)
        )
    ).all()
    if not rows:
        return {"skill_group_id": sg.id, "dispatcher_id": None, "owner_id": None}
    dispatcher = next((u for link, u in rows if link.is_dispatcher), None)
    owner = rows[0][1]  # 排序对接人优先 → 默认处理人
    return {
        "skill_group_id": sg.id,
        "dispatcher_id": dispatcher.id if dispatcher else None,
        "owner_id": owner.id,
    }


async def resolve_responsibility(db: AsyncSession, category_id: int | None) -> dict:
    """建单责任预填统一入口：链优先，无链回退旧 category_routing_rules。

    返回结构在旧 resolve_rule 基础上扩展：
      via: "chain" | "rule" | None
      chain_steps / chain_matched_category_id: 链命中时非空（建单写入快照用）
    """
    chain = await resolve_chain(db, category_id)
    if chain is not None:
        steps = chain["steps"]
        dept_code = steps[0]["department_code"] if steps else None
        rx = await prescribe_dept(db, dept_code) if dept_code else None
        sg_id = rx["skill_group_id"] if rx else None
        dispatcher_id = rx["dispatcher_id"] if rx else None
        owner_id = rx["owner_id"] if rx else None
        reason = None
        if rx is None:
            reason = f"链首部门不存在：{dept_code}，请手动指定对接部门"
        elif dispatcher_id is None:
            reason = f"部门「{dept_code}」暂无对接人，请手动指定部门对接人"
        return {
            "category_id": category_id,
            "matched": True,
            "via": "chain",
            "matched_rule_category_id": chain["matched_category_id"],
            "reason": reason,
            "chain_steps": steps,
            "dispatcher_skill_group_id": sg_id,
            "dispatcher_skill_group_name": dept_code,
            "dispatcher_id": dispatcher_id,
            "dispatcher_name": None,  # 需要展示时由调用方 join；预填只用 id
            "handler_skill_group_id": sg_id,
            "handler_skill_group_name": dept_code,
            "owner_id": owner_id,
            "owner_name": None,
        }

    # 无链 → 旧规则双轨回退
    from app.services.routing import resolve_rule

    out = await resolve_rule(db, category_id)
    out["via"] = "rule" if out.get("matched") else None
    out["chain_steps"] = None
    out["chain_matched_category_id"] = None
    return out


def build_chain_snapshot(steps: list[dict]) -> tuple[list[dict], int]:
    """展开链快照：写入 ticket.dispatch_chain_steps / dispatch_step_index。"""
    return steps, 0


async def category_children(db: AsyncSession, category_id: int) -> list[TicketCategory]:
    """分类的启用下级（分诊候选项，按展示顺序）。"""
    result = await db.execute(
        select(TicketCategory)
        .where(
            TicketCategory.parent_id == category_id,
            TicketCategory.is_active == True,  # noqa: E712
        )
        .order_by(TicketCategory.sort_order, TicketCategory.id)
    )
    return list(result.scalars().all())


async def judging_department(db: AsyncSession, category_id: int | None) -> str | None:
    """判断部门 = 该分类链的第 1 步部门（设计 §2：链首即在此判断/承接的部门）。

    业务保障(2301) 链首=售后 → 售后是第 2 级判断人；
    星座大系统(2310) 链首=星座大系统负责人 → 其为第 3 级判断人。
    无链返回 None（该分类不可分诊）。
    """
    chain = await resolve_chain(db, category_id)
    if chain is None or not chain["steps"]:
        return None
    return chain["steps"][0]["department_code"]


async def is_dept_member(
    db: AsyncSession, user_id: int, department_code: str
) -> bool:
    """用户是否为部门生效成员（不区分对接人/处理人角色，判断按部门）。"""
    sg = await get_dept(db, department_code)
    if sg is None:
        return False
    now = datetime.now(timezone.utc)
    link = (
        await db.execute(
            select(UserSkillGroup)
            .join(User, User.id == UserSkillGroup.user_id)
            .where(
                UserSkillGroup.user_id == user_id,
                UserSkillGroup.skill_group_id == sg.id,
                User.is_active == True,  # noqa: E712
                or_(
                    UserSkillGroup.effective_from.is_(None),
                    UserSkillGroup.effective_from <= now,
                ),
                or_(
                    UserSkillGroup.effective_to.is_(None),
                    UserSkillGroup.effective_to >= now,
                ),
            )
        )
    ).scalar_one_or_none()
    return link is not None
