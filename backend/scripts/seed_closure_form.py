"""Idempotent closure form for the customer-service closeout node (v3).

v2 修正了 v1 把两个独立事实合并的问题：v1 用单个「回访标记」决定
``Ticket.is_callbacked``，并把 ``Ticket.callback_required`` 同步成同一个值，
从而抹掉了「需要回访 = true / 已回访 = false」这个合法状态，并让 pending_callback
统计失真。v2 起（v3 继续沿用）：

  callback_required —— 是否要求回访，由更早的流程确定，Closure 只读展示、不改写；
  is_callbacked    —— 是否实际完成回访，Closure 记录的事实（唯一可写的回访字段）。

其余字段归属：
  满意度 / 不满原因 / 回访记录 -> Ticket 既有列（当前真值）
  关单结果 / 客户是否认可      -> Ticket 正式列（KPI 面向）
  other 补充说明              -> Submission.data（补充说明，非独立真值）
  办结时间 / 办结人工号       -> closed_at / TicketStateLog.operator_id（系统生成）

已发布版本不可原地修改，因此这是新版本；v1 的绑定会被显式停用，避免误命中。
"""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow `python scripts/seed_closure_form.py` (script dir, not the backend root).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import async_session
from app.models.node_form import FormBinding, FormDefinition, FormFieldDefinition

FORM_CODE = "closure_v3"
SUPERSEDED_CODES = ("closure_v1", "closure_v2")

RESULT_OPTIONS = [
    "recovered",
    "explained",
    "customer_abandoned",
    "terminal_hardware_damage",
    "environment_obstruction",
    "other",
]
RESULT_LABELS = {
    "recovered": "已恢复",
    "explained": "已解释说明",
    "customer_abandoned": "客户放弃",
    "terminal_hardware_damage": "终端硬件损坏",
    "environment_obstruction": "环境受阻",
    "other": "其他",
}
SATISFACTION_OPTIONS = ["satisfied", "average", "dissatisfied", "unrated"]
SATISFACTION_LABELS = {
    "satisfied": "满意",
    "average": "一般",
    "dissatisfied": "不满意",
    "unrated": "未评价",
}

# 只读上下文条件：条件值由后端从 Ticket 事实提供，客户端不能提交该字段，
# 因此表单无法被用来翻转「是否要求回访」。
CALLBACK_REQUIRED = {"field_equals": {"field": "callback_required", "value": True}}
CALLBACK_DONE = {"field_equals": {"field": "callback_completed", "value": True}}
DISSATISFIED = {"field_equals": {"field": "satisfaction", "value": "dissatisfied"}}
OTHER_RESULT = {"field_equals": {"field": "closure_result", "value": "other"}}

# (key, label, type, required, options, option_labels, visibility, required_when,
#  storage, storage_key, max_length)
FIELDS = [
    ("callback_completed", "是否已完成回访", "boolean", True, None, None,
     CALLBACK_REQUIRED, None, "ticket_field", "is_callbacked", None),
    # 回访完成之前，客户侧结论（认可 / 满意度 / 不满原因）都还不成立，一律不出现。
    ("callback_details", "回访记录", "textarea", False, None, None, CALLBACK_DONE, None,
     "ticket_field", "callback_details", 2000),
    ("satisfaction", "客户满意度评分", "select", False, SATISFACTION_OPTIONS,
     SATISFACTION_LABELS, CALLBACK_DONE, None, "ticket_field", "satisfaction", None),
    ("unsatisfied_reason", "客户不满原因", "textarea", False, None, None, CALLBACK_DONE,
     DISSATISFIED, "ticket_field", "unsatisfied_reason", 2000),
    ("customer_recognized", "客户是否认可", "boolean", True, None, None, CALLBACK_DONE, None,
     "ticket_field", "customer_recognized", None),
    ("closure_result", "关单结果", "select", True, RESULT_OPTIONS, RESULT_LABELS,
     None, None, "ticket_field", "closure_result", None),
    ("closure_result_note", "关单结果补充说明", "textarea", False, None, None, None,
     OTHER_RESULT, "submission", None, 2000),
    ("archive_notes", "归档说明", "textarea", False, None, None, None, None,
     "ticket_field", "archive_notes", 2000),
]


async def seed_closure_form(session_factory: async_sessionmaker | None = None) -> None:
    async with (session_factory or async_session)() as db:
        existing = (await db.execute(select(FormDefinition).where(
            FormDefinition.code == FORM_CODE, FormDefinition.version == 1,
        ))).scalar_one_or_none()
        if not existing:
            form = FormDefinition(code=FORM_CODE, name="客服回访闭环", node_type="closure",
                                  version=1, enabled=True, published_at=None)
            db.add(form)
            await db.flush()
            for order, row in enumerate(FIELDS):
                key, label, kind, required, options, labels, visible, required_when, storage, storage_key, limit = row
                validation: dict = {"option_labels": labels} if labels else {}
                if limit:
                    validation["max_length"] = limit
                db.add(FormFieldDefinition(
                    form_definition_id=form.id, field_key=key, label=label, field_type=kind,
                    sort_order=order, required=required, options=options,
                    validation=validation or None,
                    visibility_condition=visible, required_condition=required_when,
                    storage_type=storage, storage_key=storage_key,
                ))
            await db.flush()
            form.published_at = datetime.now(timezone.utc)

        # 绑定始终指向当前版本；v1 已发布不可改内容，只能停用其绑定，
        # 避免有人停用新版本后误命中已废弃的 v1。
        superseded_ids = (await db.execute(
            select(FormDefinition.id).where(FormDefinition.code.in_(SUPERSEDED_CODES))
        )).scalars().all()
        if superseded_ids:
            await db.execute(
                update(FormBinding)
                .where(FormBinding.node_type == "closure",
                       FormBinding.form_definition_id.in_(superseded_ids))
                .values(enabled=False)
            )
        target_id = (await db.execute(select(FormDefinition).where(
            FormDefinition.code == FORM_CODE, FormDefinition.version == 1,
        ))).scalar_one().id
        binding = (await db.execute(select(FormBinding).where(
            FormBinding.node_type == "closure", FormBinding.form_definition_id == target_id,
            FormBinding.department_code.is_(None), FormBinding.category_id.is_(None),
        ))).scalars().first()
        if binding is None:
            db.add(FormBinding(node_type="closure", department_code=None, category_id=None,
                               category_match_type="exact", form_definition_id=target_id,
                               priority=1, enabled=True))
        else:
            binding.enabled = True
        await db.commit()


if __name__ == "__main__":
    asyncio.run(seed_closure_form())
