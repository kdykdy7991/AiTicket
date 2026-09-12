"""poc workflow contract

把客服工单库改造成 POC 质量问题闭环库：

1. 用户角色收敛为 admin/presales/approver/taskforce/subsystem/quality
2. 工单状态收敛为 POC 12 状态，优先级收敛为 p0—p3
3. tickets 增加 POC 全部业务字段、人员外键、state_version、return_to_state
4. ticket_state_logs 增加动作、意见、payload 快照、状态版本、责任角色快照
5. article_attachments 增加 ticket_id/stage/uploader_id，支持创建阶段附件
6. 旧客服工单数据标记为非 POC 历史数据（legacy_state 非空，状态置为 cancelled）

Revision ID: c9f1a2b3d4e5
Revises: a1b2c3d4e5f6
Create Date: 2026-09-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c9f1a2b3d4e5"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


POC_ROLES = ("admin", "presales", "approver", "taskforce", "subsystem", "quality")
POC_STATES = (
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
POC_PRIORITIES = ("p0_blocker", "p1_critical", "p2_normal", "p3_low")

# 旧优先级 -> 新优先级（仅用于历史数据，业务代码不得依赖）
PRIORITY_UPGRADE = {
    "p1_urgent": "p1_critical",
    "p2_high": "p1_critical",
    "p3_normal": "p2_normal",
    "p4_enterprise": "p3_low",
}
PRIORITY_DOWNGRADE = {
    "p0_blocker": "p1_urgent",
    "p1_critical": "p1_urgent",
    "p2_normal": "p3_normal",
    "p3_low": "p4_enterprise",
}

# 旧客服工单列：新业务代码不再使用，放开 NOT NULL 以免 ORM 必须继续写值
LEGACY_NOT_NULL_COLUMNS = {
    "tickets": [
        "channel",
        "customer_type",
        "customer_phone",
        "is_duplicate",
        "is_escalated",
        "sla_first_response_breached",
        "sla_solution_breached",
        "resolved",
        "callback_required",
        "is_callbacked",
    ],
}

NEW_TICKET_COLUMNS = [
    # 创建阶段
    sa.Column("product_line", sa.String(length=100), nullable=True),
    sa.Column("problem_type", sa.String(length=100), nullable=True),
    sa.Column("closure_requirement", sa.Text(), nullable=True),
    sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("location", sa.String(length=300), nullable=True),
    sa.Column("longitude", sa.Numeric(10, 7), nullable=True),
    sa.Column("latitude", sa.Numeric(10, 7), nullable=True),
    sa.Column("device_info", sa.Text(), nullable=True),
    sa.Column("approver_id", sa.BigInteger(), nullable=True),
    sa.Column("creator_department", sa.String(length=100), nullable=True),
    # 后续阶段
    sa.Column("confirmation_comment", sa.Text(), nullable=True),
    sa.Column("subsystem_owner_id", sa.BigInteger(), nullable=True),
    sa.Column("acceptance_comment", sa.Text(), nullable=True),
    sa.Column("temporary_measure", sa.Text(), nullable=True),
    sa.Column("long_term_measure", sa.Text(), nullable=True),
    sa.Column("planned_completion_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("plan_confirmation_comment", sa.Text(), nullable=True),
    sa.Column("initial_investigation", sa.Text(), nullable=True),
    sa.Column("root_cause", sa.Text(), nullable=True),
    sa.Column("analysis_report", sa.Text(), nullable=True),
    sa.Column("actual_completion_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("verification_status", sa.String(length=30), nullable=True),
    sa.Column("verification_conclusion", sa.Text(), nullable=True),
    sa.Column("quality_review_result", sa.Text(), nullable=True),
    sa.Column("defect_id", sa.String(length=100), nullable=True),
    sa.Column("defect_repository_path", sa.String(length=1000), nullable=True),
    sa.Column("defect_registered_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("defect_registered_by_id", sa.BigInteger(), nullable=True),
    # 流程控制
    sa.Column(
        "state_version", sa.Integer(), nullable=False, server_default=sa.text("1")
    ),
    sa.Column("return_to_state", sa.String(length=40), nullable=True),
    # 非 POC 历史数据标记（migration-only，不出现在任何接口）
    sa.Column("legacy_state", sa.String(length=30), nullable=True),
]

NEW_LOG_COLUMNS = [
    sa.Column("action", sa.String(length=40), nullable=True),
    sa.Column("comment", sa.Text(), nullable=True),
    sa.Column("payload_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("state_version", sa.Integer(), nullable=True),
    sa.Column("responsible_role_snapshot", sa.String(length=20), nullable=True),
    sa.Column("responsible_user_id_snapshot", sa.BigInteger(), nullable=True),
]


def upgrade() -> None:
    bind = op.get_bind()

    # ── 1. 用户角色收敛 ───────────────────────────────────
    op.execute(
        sa.text(
            """
            UPDATE users
               SET role = CASE
                     WHEN role = 'agent' THEN 'presales'
                     WHEN role = 'handler' THEN 'subsystem'
                     WHEN role IN ('admin','presales','approver','taskforce','subsystem','quality')
                       THEN role
                     ELSE 'presales'
                   END
            """
        )
    )
    op.execute(sa.text("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_role_poc"))
    op.create_check_constraint(
        "ck_users_role_poc",
        "users",
        "role IN ('admin','presales','approver','taskforce','subsystem','quality')",
    )

    # ── 2. 旧客服工单：标记为历史数据 ─────────────────────
    # 新业务代码不再使用的旧列放开 NOT NULL，避免 ORM 必须继续写旧字段
    for column in LEGACY_NOT_NULL_COLUMNS["tickets"]:
        op.execute(sa.text(f"ALTER TABLE tickets ALTER COLUMN {column} DROP NOT NULL"))

    # ── 3. tickets 新字段 ─────────────────────────────────
    for column in NEW_TICKET_COLUMNS:
        op.add_column("tickets", column)
    op.create_foreign_key(
        "fk_tickets_approver_id_users",
        "tickets",
        "users",
        ["approver_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_tickets_subsystem_owner_id_users",
        "tickets",
        "users",
        ["subsystem_owner_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_tickets_defect_registered_by_id_users",
        "tickets",
        "users",
        ["defect_registered_by_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ── 4. 历史工单数据处理 ───────────────────────────────
    # 规则：任何迁移前已存在的工单都不是 POC 工单，统一标记 legacy_state 并置为
    # cancelled 终态，绝不把旧状态映射成新流程的审批结果。
    op.execute(
        sa.text(
            """
            UPDATE tickets
               SET legacy_state = state,
                   state = 'cancelled',
                   closed_at = COALESCE(closed_at, updated_at, now()),
                   state_version = 1
             WHERE legacy_state IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE tickets
               SET priority = CASE priority
                     WHEN 'p1_urgent' THEN 'p1_critical'
                     WHEN 'p2_high' THEN 'p1_critical'
                     WHEN 'p3_normal' THEN 'p2_normal'
                     WHEN 'p4_enterprise' THEN 'p3_low'
                     WHEN 'p0_blocker' THEN 'p0_blocker'
                     WHEN 'p1_critical' THEN 'p1_critical'
                     WHEN 'p2_normal' THEN 'p2_normal'
                     WHEN 'p3_low' THEN 'p3_low'
                     ELSE 'p2_normal'
                   END
             WHERE legacy_state IS NOT NULL
            """
        )
    )

    # ── 5. 状态与优先级约束 ───────────────────────────────
    op.execute(
        sa.text("ALTER TABLE tickets ALTER COLUMN priority SET DEFAULT 'p2_normal'")
    )
    op.execute(sa.text("ALTER TABLE tickets DROP CONSTRAINT IF EXISTS ck_tickets_state_poc"))
    op.create_check_constraint(
        "ck_tickets_state_poc",
        "tickets",
        "state IN (" + ",".join(f"'{s}'" for s in POC_STATES) + ")",
    )
    op.execute(
        sa.text("ALTER TABLE tickets DROP CONSTRAINT IF EXISTS ck_tickets_priority_poc")
    )
    op.create_check_constraint(
        "ck_tickets_priority_poc",
        "tickets",
        "priority IN (" + ",".join(f"'{p}'" for p in POC_PRIORITIES) + ")",
    )

    # ── 6. 查询索引 ───────────────────────────────────────
    op.create_index(
        "ix_tickets_state_updated_at",
        "tickets",
        ["state", sa.text("updated_at DESC")],
    )
    op.create_index("ix_tickets_approver_state", "tickets", ["approver_id", "state"])
    op.create_index(
        "ix_tickets_subsystem_owner_state", "tickets", ["subsystem_owner_id", "state"]
    )
    op.create_index(
        "ix_tickets_skill_group_state", "tickets", ["skill_group_id", "state"]
    )
    op.create_index(
        "ix_tickets_planned_completion_at", "tickets", ["planned_completion_at"]
    )
    op.create_index("ix_tickets_defect_id", "tickets", ["defect_id"])
    op.create_index(
        "ix_tickets_is_draft_creator", "tickets", ["is_draft", "creator_id"]
    )

    # ── 7. 流程日志字段 ───────────────────────────────────
    for column in NEW_LOG_COLUMNS:
        op.add_column("ticket_state_logs", column)
    op.create_foreign_key(
        "fk_ticket_state_logs_responsible_user_id",
        "ticket_state_logs",
        "users",
        ["responsible_user_id_snapshot"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_ticket_state_logs_ticket_id", "ticket_state_logs", ["ticket_id"]
    )

    # ── 8. 附件表支持创建阶段上传 ─────────────────────────
    op.add_column("article_attachments", sa.Column("ticket_id", sa.BigInteger(), nullable=True))
    op.add_column("article_attachments", sa.Column("stage", sa.String(length=40), nullable=True))
    op.add_column("article_attachments", sa.Column("uploader_id", sa.BigInteger(), nullable=True))
    op.alter_column("article_attachments", "article_id", nullable=True)
    op.execute(
        sa.text(
            """
            UPDATE article_attachments a
               SET ticket_id = r.ticket_id,
                   uploader_id = r.sender_id
              FROM articles r
             WHERE a.article_id = r.id
            """
        )
    )
    op.create_foreign_key(
        "fk_article_attachments_ticket_id",
        "article_attachments",
        "tickets",
        ["ticket_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_article_attachments_uploader_id",
        "article_attachments",
        "users",
        ["uploader_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_article_attachments_ticket_id", "article_attachments", ["ticket_id"]
    )

    _ = bind  # 全部通过 op.execute 执行，保留 bind 以便后续扩展


def downgrade() -> None:
    # ── 附件表回退 ────────────────────────────────────────
    op.execute(sa.text("DELETE FROM article_attachments WHERE article_id IS NULL"))
    op.drop_index("ix_article_attachments_ticket_id", table_name="article_attachments")
    op.drop_constraint(
        "fk_article_attachments_uploader_id", "article_attachments", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_article_attachments_ticket_id", "article_attachments", type_="foreignkey"
    )
    op.alter_column("article_attachments", "article_id", nullable=False)
    op.drop_column("article_attachments", "uploader_id")
    op.drop_column("article_attachments", "stage")
    op.drop_column("article_attachments", "ticket_id")

    # ── 流程日志字段回退 ──────────────────────────────────
    op.drop_index("ix_ticket_state_logs_ticket_id", table_name="ticket_state_logs")
    op.drop_constraint(
        "fk_ticket_state_logs_responsible_user_id",
        "ticket_state_logs",
        type_="foreignkey",
    )
    for column in reversed(NEW_LOG_COLUMNS):
        op.drop_column("ticket_state_logs", column.name)

    # ── 索引回退 ──────────────────────────────────────────
    op.drop_index("ix_tickets_is_draft_creator", table_name="tickets")
    op.drop_index("ix_tickets_defect_id", table_name="tickets")
    op.drop_index("ix_tickets_planned_completion_at", table_name="tickets")
    op.drop_index("ix_tickets_skill_group_state", table_name="tickets")
    op.drop_index("ix_tickets_subsystem_owner_state", table_name="tickets")
    op.drop_index("ix_tickets_approver_state", table_name="tickets")
    op.drop_index("ix_tickets_state_updated_at", table_name="tickets")

    # ── 约束回退 ──────────────────────────────────────────
    op.drop_constraint("ck_tickets_priority_poc", "tickets", type_="check")
    op.drop_constraint("ck_tickets_state_poc", "tickets", type_="check")
    op.execute(sa.text("ALTER TABLE tickets ALTER COLUMN priority DROP DEFAULT"))

    # ── 历史数据回退 ──────────────────────────────────────
    op.execute(
        sa.text(
            """
            UPDATE tickets
               SET priority = CASE priority
                     WHEN 'p0_blocker' THEN 'p1_urgent'
                     WHEN 'p1_critical' THEN 'p1_urgent'
                     WHEN 'p2_normal' THEN 'p3_normal'
                     WHEN 'p3_low' THEN 'p4_enterprise'
                     ELSE priority
                   END
             WHERE legacy_state IS NOT NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE tickets
               SET state = COALESCE(legacy_state, 'pending')
             WHERE legacy_state IS NOT NULL
            """
        )
    )

    # ── tickets 列回退 ────────────────────────────────────
    op.drop_constraint("fk_tickets_defect_registered_by_id_users", "tickets", type_="foreignkey")
    op.drop_constraint("fk_tickets_subsystem_owner_id_users", "tickets", type_="foreignkey")
    op.drop_constraint("fk_tickets_approver_id_users", "tickets", type_="foreignkey")
    for column in reversed(NEW_TICKET_COLUMNS):
        op.drop_column("tickets", column.name)

    # ── 旧客服列恢复 NOT NULL ─────────────────────────────
    op.execute(sa.text("UPDATE tickets SET channel = 'phone' WHERE channel IS NULL"))
    op.execute(sa.text("UPDATE tickets SET customer_type = 'personal' WHERE customer_type IS NULL"))
    op.execute(sa.text("UPDATE tickets SET customer_phone = '' WHERE customer_phone IS NULL"))
    for column in LEGACY_NOT_NULL_COLUMNS["tickets"]:
        if column in ("channel", "customer_type", "customer_phone"):
            continue
        op.execute(sa.text(f"UPDATE tickets SET {column} = false WHERE {column} IS NULL"))
    for column in LEGACY_NOT_NULL_COLUMNS["tickets"]:
        op.execute(sa.text(f"ALTER TABLE tickets ALTER COLUMN {column} SET NOT NULL"))

    # ── 用户角色回退 ──────────────────────────────────────
    op.drop_constraint("ck_users_role_poc", "users", type_="check")
    op.execute(
        sa.text(
            """
            UPDATE users
               SET role = CASE
                     WHEN role = 'presales' THEN 'agent'
                     WHEN role = 'subsystem' THEN 'handler'
                     WHEN role = 'approver' THEN 'handler'
                     WHEN role = 'taskforce' THEN 'handler'
                     WHEN role = 'quality' THEN 'handler'
                     ELSE role
                   END
            """
        )
    )
