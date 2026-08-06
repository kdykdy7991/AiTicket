"""把"已归档 + 未回访 + 标记为需回访"的历史工单同步为"无需回访"。

背景：归档面板原只有"已回访/未回访"两态。引入"无需回访"（callback_required=false）后，
历史上在归档时选了"未回访"的工单，语义上应视为"无需回访"——因为工单已归档即终态，
不存在"待回访"待办（待回访指标只统计 resolved 状态，见 common.py 的 pending_callback）。

幂等：只处理 state='archived' AND is_callbacked=false AND callback_required=true 的工单，
改完一遍后条件不再匹配，可重复执行。不会触碰 resolved/其他状态工单，
不影响"待回访工单"指标。

用法（与 update_seed_data.py 一致，通过 DATABASE_URL 环境变量连接）：
    python scripts/sync_archived_callback.py
"""

import asyncio
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://skdy:skdy123@localhost:5433/skdy_ticket")

engine = create_async_engine(DATABASE_URL, future=True)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def main() -> None:
    async with async_session() as db:
        # 先预览将要修改的工单
        rows = (await db.execute(text("""
            SELECT id, number FROM tickets
            WHERE state = 'archived' AND is_callbacked = false AND callback_required = true
            ORDER BY id
        """))).all()
        print(f"待修正为「无需回访」的已归档工单数：{len(rows)}")
        for r in rows:
            print(f"  - #{r.id} {r.number}")

        if not rows:
            print("无需修改。")
            return

        result = await db.execute(text("""
            UPDATE tickets
            SET callback_required = false, updated_at = now()
            WHERE state = 'archived' AND is_callbacked = false AND callback_required = true
        """))
        await db.commit()
        print(f"已更新 {result.rowcount} 条工单：callback_required = false（无需回访）")


if __name__ == "__main__":
    asyncio.run(main())
