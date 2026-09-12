"""final approval step

流程调整（业务方确认）：

- 删除「待缺陷入库」节点与 `register_defect` 动作：缺陷入库在 SVN 侧完成，不作为
  工单系统内的流转节点，工单也不再记录缺陷 ID / SVN 路径。
- 质量评审通过后新增「待批准人复核」节点（`pending_final_approval`），由工单指定的
  批准人执行 `approve_closure` 批准闭环；批准人可以驳回（退回质量重新评审）。

因此：
- `pass_review` 目标由 `pending_defect_registration` 改为 `pending_final_approval`
- 删除缺陷相关四列（含外键与索引）
- 在途数据与历史日志按同一映射改写，并重建状态 CHECK 约束

契约：docs/poc/00_poc_workflow_development_contract.md 第 3 节。

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-09-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a8b9c0d1e2f3"
down_revision: Union[str, None] = "f7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


#: 本次调整前的状态列表
OLD_POC_STATES = (
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

#: 本次调整后的状态列表
NEW_POC_STATES = (
    "pending_approval",
    "pending_routing",
    "planning",
    "pending_plan_confirmation",
    "processing",
    "pending_quality_review",
    "pending_final_approval",
    "closed",
    "returned",
    "cancelled",
)

#: 被替换的状态 -> 新状态
STATE_REMAP = {"pending_defect_registration": "pending_final_approval"}


def _recreate_state_constraint(states: tuple[str, ...]) -> None:
    op.execute(sa.text("ALTER TABLE tickets DROP CONSTRAINT IF EXISTS ck_tickets_state_poc"))
    op.create_check_constraint(
        "ck_tickets_state_poc",
        "tickets",
        "state IN (" + ",".join(f"'{s}'" for s in states) + ")",
    )


def upgrade() -> None:
    # ── 1. 放开约束，写入新状态 ───────────────────────────
    op.execute(sa.text("ALTER TABLE tickets DROP CONSTRAINT IF EXISTS ck_tickets_state_poc"))

    # ── 2. 在途工单状态改写（待缺陷入库 -> 待批准人复核）──
    for old, new in STATE_REMAP.items():
        op.execute(
            sa.text("UPDATE tickets SET state = :new WHERE state = :old").bindparams(
                new=new, old=old
            )
        )

    # ── 3. 历史日志同步改写 ──────────────────────────────
    for old, new in STATE_REMAP.items():
        for column in ("from_state", "to_state"):
            op.execute(
                sa.text(
                    f"UPDATE ticket_state_logs SET {column} = :new WHERE {column} = :old"
                ).bindparams(new=new, old=old)
            )
    # 历史动作编码 register_defect 保留在日志中（时间线按「历史动作」展示）

    # ── 4. 删除缺陷相关列（含外键与索引）─────────────────
    op.execute(sa.text("DROP INDEX IF EXISTS ix_tickets_defect_id"))
    op.drop_constraint(
        "fk_tickets_defect_registered_by_id_users", "tickets", type_="foreignkey"
    )
    for column in (
        "defect_registered_by_id",
        "defect_registered_at",
        "defect_repository_path",
        "defect_id",
    ):
        op.drop_column("tickets", column)

    # ── 5. 重建状态约束 ──────────────────────────────────
    _recreate_state_constraint(NEW_POC_STATES)


def downgrade() -> None:
    """恢复列结构并还原状态编码。

    缺陷列的历史数据无法恢复（已随列删除），重新加入后为空值。
    """
    op.execute(sa.text("ALTER TABLE tickets DROP CONSTRAINT IF EXISTS ck_tickets_state_poc"))

    op.add_column("tickets", sa.Column("defect_id", sa.String(length=100), nullable=True))
    op.add_column(
        "tickets", sa.Column("defect_repository_path", sa.String(length=1000), nullable=True)
    )
    op.add_column(
        "tickets", sa.Column("defect_registered_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("tickets", sa.Column("defect_registered_by_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_tickets_defect_registered_by_id_users",
        "tickets",
        "users",
        ["defect_registered_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_tickets_defect_id", "tickets", ["defect_id"])

    for old, new in STATE_REMAP.items():
        op.execute(
            sa.text("UPDATE tickets SET state = :old WHERE state = :new").bindparams(
                new=new, old=old
            )
        )
        for column in ("from_state", "to_state"):
            op.execute(
                sa.text(
                    f"UPDATE ticket_state_logs SET {column} = :old WHERE {column} = :new"
                ).bindparams(new=new, old=old)
            )

    _recreate_state_constraint(OLD_POC_STATES)
