"""merge taskforce steps

把「待问题确认 / 待流转 / 待分系统接收」三个节点合并为一步：
专项小组确认问题描述并选定分系统与分系统负责人，通过即流转到分系统
（直接进入 `planning` 闭环计划制定中），不通过则退回。

- 删除状态 `pending_confirmation`、`pending_acceptance`
- 删除动作 `confirm_problem`、`accept`
- `approve` 目标由 `pending_confirmation` 改为 `pending_routing`
- `route` 目标由 `pending_acceptance` 改为 `planning`，并可携带 `confirmation_comment`
- 在途数据与历史日志按同一映射改写，保证状态值仍在约束内

契约：docs/poc/00_poc_workflow_development_contract.md 第 3 节。

Revision ID: f7a8b9c0d1e2
Revises: e5f6a7b8c9d0
Create Date: 2026-09-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


#: 合并前的状态列表（用于 downgrade 还原约束）
OLD_POC_STATES = (
    "pending_approval",
    "pending_confirmation",
    "pending_routing",
    "pending_acceptance",
    "planning",
    "pending_plan_confirmation",
    "processing",
    "pending_quality_review",
    "pending_defect_registration",
    "closed",
    "returned",
    "cancelled",
)

#: 合并后的状态列表
NEW_POC_STATES = (
    "pending_approval",
    "pending_routing",
    "planning",
    "pending_plan_confirmation",
    "processing",
    "pending_quality_review",
    "pending_defect_registration",
    "closed",
    "returned",
    "cancelled",
)

#: 被合并掉的状态 -> 合并后的状态
STATE_MERGE = {
    "pending_confirmation": "pending_routing",
    "pending_acceptance": "planning",
}


def _recreate_state_constraint(states: tuple[str, ...]) -> None:
    op.execute(sa.text("ALTER TABLE tickets DROP CONSTRAINT IF EXISTS ck_tickets_state_poc"))
    op.create_check_constraint(
        "ck_tickets_state_poc",
        "tickets",
        "state IN (" + ",".join(f"'{s}'" for s in states) + ")",
    )


def upgrade() -> None:
    # ── 1. 先放开约束，才能写入合并后的状态 ────────────────
    op.execute(sa.text("ALTER TABLE tickets DROP CONSTRAINT IF EXISTS ck_tickets_state_poc"))

    # ── 2. 在途工单状态改写 ───────────────────────────────
    for old, new in STATE_MERGE.items():
        op.execute(
            sa.text("UPDATE tickets SET state = :new WHERE state = :old").bindparams(
                new=new, old=old
            )
        )
    # 退回目标只可能是 pending_approval / planning / processing，无需改写

    # ── 3. 历史流程日志的 from/to 同步改写 ────────────────
    # 日志本身不可变，但状态编码必须仍可解析，否则时间线无法渲染
    for old, new in STATE_MERGE.items():
        for column in ("from_state", "to_state"):
            op.execute(
                sa.text(
                    f"UPDATE ticket_state_logs SET {column} = :new WHERE {column} = :old"
                ).bindparams(new=new, old=old)
            )
    # 已撤销的旧动作编码保留在日志里（时间线按「历史动作」展示），不参与状态机

    # ── 4. 按合并后的状态列表重建约束 ─────────────────────
    _recreate_state_constraint(NEW_POC_STATES)


def downgrade() -> None:
    """状态合并不可逆：仅还原约束（合并后的状态在两个列表中都存在）。

    已合并的工单不会退回 `pending_confirmation` / `pending_acceptance`，
    需要旧流程时请从备份恢复。
    """
    op.execute(sa.text("ALTER TABLE tickets DROP CONSTRAINT IF EXISTS ck_tickets_state_poc"))
    _recreate_state_constraint(OLD_POC_STATES)
