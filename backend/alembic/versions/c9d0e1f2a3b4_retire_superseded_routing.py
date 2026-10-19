"""Retire routing rules and placeholder members superseded by dispatch chains.

The service complaint fallback remains in place for important/major complaints.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, Sequence[str], None] = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


RETIRED_CATEGORIES = (1202, 1203, 1204, 2201, 2301, 2311, 2312, 2313)
RETIRED_USERS = (201, 202, 203, 210, 211, 212, 213, 214)
RETIRED_GROUPS = (101, 102, 103, 105, 106)


def upgrade() -> None:
    bind = op.get_bind()
    # Refuse to remove the parent fallback while a ticket still sits at 2201.
    if bind.execute(sa.text("SELECT count(*) FROM tickets WHERE category_id = 2201")).scalar_one():
        raise RuntimeError("业务运营 2201 仍有工单；先处理历史分类再清理旧路由")

    existing_rules = set(bind.execute(sa.text(
        "SELECT category_id FROM category_routing_rules WHERE category_id = ANY(:ids)"
    ), {"ids": list(RETIRED_CATEGORIES)}).scalars())
    required_chains = set(existing_rules) - {2201}
    if 2201 in existing_rules:
        required_chains.update((2203, 2204))
    enabled = set(bind.execute(sa.text(
        "SELECT category_id FROM dispatch_chains WHERE enabled = true"
    )).scalars())
    missing = required_chains - enabled
    if missing:
        raise RuntimeError(f"正式分派链缺失，停止旧路由清理: {sorted(missing)}")
    expected_users = {
        201: "v2_dispatcher_ops", 202: "v2_dispatcher_assurance",
        203: "v2_dispatcher_instant", 210: "v2_owner_ops",
        211: "v2_owner_assurance", 212: "v2_owner_core",
        213: "v2_owner_tt", 214: "v2_owner_satellite",
    }
    expected_groups = {
        101: "业务运营组", 102: "业务保障组", 103: "核心网组",
        105: "卫星组", 106: "即时办结咨询组",
    }
    for user_id, username in bind.execute(sa.text(
        "SELECT id, username FROM users WHERE id = ANY(:ids)"
    ), {"ids": list(RETIRED_USERS)}):
        if username != expected_users[user_id]:
            raise RuntimeError(f"用户 ID {user_id} 已由其他账号占用: {username}")
    for group_id, name in bind.execute(sa.text(
        "SELECT id, name FROM skill_groups WHERE id = ANY(:ids)"
    ), {"ids": list(RETIRED_GROUPS)}):
        if name != expected_groups[group_id]:
            raise RuntimeError(f"部门 ID {group_id} 已由其他部门占用: {name}")

    # Preserve history: do not rely on SET NULL or CASCADE for other business references.
    user_refs = (
        ("tickets", "creator_id"), ("tickets", "dispatcher_id"),
        ("tickets", "first_owner_id"), ("tickets", "owner_id"),
        ("tickets", "returned_to_user_id"), ("tickets", "urged_by_id"),
        ("articles", "sender_id"), ("reminders", "sender_id"),
        ("ticket_state_logs", "creator_id_snapshot"),
        ("ticket_state_logs", "dispatcher_id_snapshot"),
        ("ticket_state_logs", "owner_id_snapshot"),
        ("ticket_state_logs", "operator_id"),
        ("ticket_node_submissions", "operator_id"),
        ("dingtalk_notifications", "target_user_id"), ("audit_logs", "user_id"),
    )
    group_refs = (
        ("tickets", "skill_group_id"), ("tickets", "handler_skill_group_id"),
        ("sla_policies", "skill_group_id"),
        ("complaint_escalation_policies", "notify_skill_group_id"),
        ("ticket_node_submissions", "department_id"),
    )
    for table, column in user_refs:
        count = bind.execute(sa.text(
            f"SELECT count(*) FROM {table} WHERE {column} = ANY(:ids)"
        ), {"ids": list(RETIRED_USERS)}).scalar_one()
        if count:
            raise RuntimeError(f"旧 v2 用户仍被 {table}.{column} 引用: {count}")
    for table, column in group_refs:
        count = bind.execute(sa.text(
            f"SELECT count(*) FROM {table} WHERE {column} = ANY(:ids)"
        ), {"ids": list(RETIRED_GROUPS)}).scalar_one()
        if count:
            raise RuntimeError(f"旧组仍被 {table}.{column} 引用: {count}")

    bind.execute(sa.text(
        "DELETE FROM category_routing_rules WHERE category_id = ANY(:ids)"
    ), {"ids": list(RETIRED_CATEGORIES)})
    bind.execute(sa.text(
        "DELETE FROM user_skill_groups WHERE user_id = ANY(:ids)"
    ), {"ids": list(RETIRED_USERS)})
    bind.execute(sa.text(
        "DELETE FROM users WHERE id = ANY(:ids)"
    ), {"ids": list(RETIRED_USERS)})
    bind.execute(sa.text(
        "DELETE FROM skill_groups WHERE id = ANY(:ids)"
    ), {"ids": list(RETIRED_GROUPS)})


def downgrade() -> None:
    # Retired seed data is intentionally not recreated. Restore from a prior
    # database backup if this migration must be reversed.
    pass
