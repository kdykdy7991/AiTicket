"""一次性脚本：清掉「对接部门 ≠ 部门对接人实际所在部门」的脏数据。

背景：PATCH /tickets/{id} 漏写 dispatcher_id 的 bug 导致：
  - skill_group_id 已是新部门
  - dispatcher_id 还是老部门的人
详情页看上去"还是老部门对接人"。

本脚本：
  1. 打印当前不一致的工单数 + 抽样
  2. 把这些工单的 dispatcher_id 置 NULL（让前端重新指派）

用法：
  cd backend && python -m scripts.fix_orphan_dispatcher
或：
  cd backend && PYTHONPATH=. python scripts/fix_orphan_dispatcher.py [--dry-run]
"""
import sys
from pathlib import Path

# 让脚本能以 `python scripts/xxx.py` 直接运行
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text

from app.core.config import settings


DIAGNOSIS_SQL = """
SELECT t.id, t.number, t.state, t.skill_group_id, sg.name AS skill_group_name,
       t.dispatcher_id, u.name AS dispatcher_name
FROM tickets t
LEFT JOIN skill_groups sg ON sg.id = t.skill_group_id
LEFT JOIN users u ON u.id = t.dispatcher_id
WHERE t.dispatcher_id IS NOT NULL
  AND t.skill_group_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM user_skill_groups usg
    WHERE usg.user_id = t.dispatcher_id
      AND usg.skill_group_id = t.skill_group_id
      AND usg.is_dispatcher = TRUE
  )
ORDER BY t.id DESC
LIMIT 50;
"""

COUNT_SQL = """
SELECT COUNT(*)
FROM tickets t
WHERE t.dispatcher_id IS NOT NULL
  AND t.skill_group_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM user_skill_groups usg
    WHERE usg.user_id = t.dispatcher_id
      AND usg.skill_group_id = t.skill_group_id
      AND usg.is_dispatcher = TRUE
  );
"""

FIX_SQL = """
UPDATE tickets
SET dispatcher_id = NULL
WHERE id IN (
  SELECT t.id
  FROM tickets t
  WHERE t.dispatcher_id IS NOT NULL
    AND t.skill_group_id IS NOT NULL
    AND NOT EXISTS (
      SELECT 1 FROM user_skill_groups usg
      WHERE usg.user_id = t.dispatcher_id
        AND usg.skill_group_id = t.skill_group_id
        AND usg.is_dispatcher = TRUE
    )
);
"""


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    # config 里是 asyncpg 驱动，一次性脚本用同步引擎更方便
    sync_url = settings.database_url.replace("postgresql+asyncpg", "postgresql+psycopg2")
    engine = create_engine(sync_url, future=True)
    with engine.begin() as conn:
        total = conn.execute(text(COUNT_SQL)).scalar() or 0
        print(f"[诊断] 不一致工单数: {total}")
        if total == 0:
            print("✅ 没有脏数据，无需修复。")
            return 0

        print("\n[抽样] 最近 50 条不一致工单：")
        print(f"{'ID':>6}  {'单号':<14} {'状态':<10} {'skill_group_id':>14}  {'对接部门':<14} {'dispatcher_id':>14}  {'对接人':<14}")
        print("-" * 110)
        rows = conn.execute(text(DIAGNOSIS_SQL)).all()
        for r in rows:
            print(
                f"{r.id:>6}  {str(r.number or ''):<14} {r.state:<10} "
                f"{r.skill_group_id:>14}  {str(r.skill_group_name or ''):<14} "
                f"{r.dispatcher_id:>14}  {str(r.dispatcher_name or ''):<14}"
            )

        if dry_run:
            print("\n[--dry-run] 未执行修复。要真的修复，把 --dry-run 去掉再跑。")
            return 0

        print(f"\n[执行] 把 {total} 条工单的 dispatcher_id 置 NULL ...")
        result = conn.execute(text(FIX_SQL))
        print(f"[完成] 受影响行数: {result.rowcount}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
