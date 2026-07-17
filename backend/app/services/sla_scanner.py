"""SLA 超时扫描引擎。

通过 FastAPI lifespan 启动的后台循环，每分钟扫描一次工单：
- 检测解决超时（非终态且未解决，超过 solution_deadline）
- 标记 sla_solution_breached

MVP 单进程实现：lifespan 起一个 asyncio task 循环。多 worker 部署时需改用 ARQ/定时任务避免重复执行。
"""

import asyncio
import logging

from sqlalchemy import select, update

from app.core.database import async_session
from app.models.ticket import Ticket

logger = logging.getLogger("sla_scanner")

SCAN_INTERVAL_SECONDS = 60  # 每分钟扫描一次

_scanner_task: asyncio.Task | None = None


async def scan_sla_breaches() -> dict:
    """扫描并标记超时工单。返回 {solution_breached} 计数。"""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)

    async with async_session() as db:
        # 解决超时：非终态、未解决、超过 deadline、且尚未标记
        sol_result = await db.execute(
            update(Ticket)
            .where(
                Ticket.state.notin_(["archived", "cancelled"]),
                Ticket.solved_at.is_(None),
                Ticket.solution_deadline.is_not(None),
                Ticket.solution_deadline < now,
                Ticket.sla_solution_breached == False,
            )
            .values(sla_solution_breached=True)
        )
        sol_count = sol_result.rowcount or 0

        await db.commit()

    if sol_count:
        logger.info("SLA 扫描：解决超时 %d 条", sol_count)

    return {"solution_breached": sol_count}


async def _scan_loop():
    """后台循环：每分钟扫描一次。"""
    logger.info("SLA 扫描引擎已启动，间隔 %ds", SCAN_INTERVAL_SECONDS)
    while True:
        try:
            await scan_sla_breaches()
        except Exception as e:
            logger.exception("SLA 扫描异常: %s", e)
        await asyncio.sleep(SCAN_INTERVAL_SECONDS)


def start_sla_scanner():
    """启动 SLA 扫描后台任务（在 FastAPI lifespan 中调用）。"""
    global _scanner_task
    if _scanner_task is None or _scanner_task.done():
        _scanner_task = asyncio.create_task(_scan_loop())


def stop_sla_scanner():
    """停止 SLA 扫描后台任务。"""
    global _scanner_task
    if _scanner_task and not _scanner_task.done():
        _scanner_task.cancel()
    _scanner_task = None
