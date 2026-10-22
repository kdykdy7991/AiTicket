"""周期扫描引擎：SLA 超时标记 + 暂缓「预计恢复时间已到」提醒。

通过 FastAPI lifespan 启动的后台循环，每分钟扫描一次工单：
- 检测解决超时（非终态且未解决，超过 solution_deadline），标记 sla_solution_breached
- 暂缓工单的预计恢复时间已到且尚未提醒过 → 发一次钉钉提醒（纯提醒，
  不改状态、不自动恢复、不涉及任何 SLA 计时/暂停/顺延/超时语义）。
  该提醒受 DINGTALK_NOTIFICATION_ENABLED 总开关控制，默认关闭；关闭时
  scan_hold_expiries() 在入口直接返回，不查库、不发送、不写任何字段，
  暂缓主流程（保持 on_hold，由处理人 resume）完全不受影响。

MVP 单进程实现：lifespan 起一个 asyncio task 循环。多 worker 部署时需改用 ARQ/定时任务避免重复执行。
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import async_session
from app.models.ticket import Ticket, TicketStateLog
from app.models.sla import SLARound

logger = logging.getLogger("sla_scanner")

SCAN_INTERVAL_SECONDS = 60  # 每分钟扫描一次

_scanner_task: asyncio.Task | None = None


async def scan_sla_breaches() -> dict:
    """扫描并标记超时工单。返回 {solution_breached} 计数。"""
    now = datetime.now(timezone.utc)

    async with async_session() as db:
        # TODO(sla-policy): on_hold 暂不排除，超时仍会标记。
        # 等 SLA 策略定稿后再决定：
        #   - 暂停计时：进出 on_hold 时推 solution_deadline
        #   - 扫描跳过：把 on_hold 加进 notin_ 列表
        #   - 用 hold_until 控表：now < hold_until 时跳过
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

        await db.execute(
            update(SLARound)
            .where(SLARound.status == "running", SLARound.deadline_at < now,
                   SLARound.breached == False)
            .values(breached=True)
        )

        await db.commit()

    if sol_count:
        logger.info("SLA 扫描：解决超时 %d 条", sol_count)

    return {"solution_breached": sol_count}


async def _latest_hold_reason(db, ticket_id: int) -> str | None:
    """暂缓原因复用最新一条 hold Flow Log 的 reason，不为展示新增 Ticket 列。"""
    log = (await db.execute(
        select(TicketStateLog.reason)
        .where(TicketStateLog.ticket_id == ticket_id,
               TicketStateLog.action_type == "hold")
        .order_by(TicketStateLog.id.desc()).limit(1)
    )).scalar_one_or_none()
    return log


async def scan_hold_expiries(session_factory=None) -> dict:
    """提醒「预计恢复时间已到」的暂缓工单，每轮暂缓最多一次。

    命中条件：on_hold + hold_until 已到 + 尚未提醒过（hold_reminded_at IS NULL）。
    只发提醒；工单继续保持 on_hold，不自动 resume / resolve / transfer / upgrade，
    也不触碰任何 SLA 字段。

    ``hold_reminded_at`` 的语义是「本轮暂缓的预计恢复提醒实际成功发送的时间」，
    不是「scanner 处理过」：发送失败不落值，下一轮继续重试（失败记录已落在
    DingtalkNotification）。恢复处理会清空它，因此每轮暂缓最多成功提醒一次。

    外部通知总开关（DINGTALK_NOTIFICATION_ENABLED）关闭时在入口直接返回，
    不进行任何数据库查询——默认关闭状态下几乎没有额外运行成本。

    ``session_factory`` 可注入（测试用）；生产走模块级 async_session。
    """
    from app.services.notification import remind_hold_expiry

    if not settings.DINGTALK_NOTIFICATION_ENABLED:
        return {"hold_expiry_reminded": 0}

    factory = session_factory or async_session
    now = datetime.now(timezone.utc)
    reminded = 0
    async with factory() as db:
        tickets = (await db.execute(
            select(Ticket)
            .where(
                Ticket.state == "on_hold",
                Ticket.hold_until.is_not(None),
                Ticket.hold_until <= now,
                Ticket.hold_reminded_at.is_(None),
            )
            .options(selectinload(Ticket.owner), selectinload(Ticket.skill_group))
        )).scalars().all()
        for ticket in tickets:
            result = await remind_hold_expiry(
                ticket, await _latest_hold_reason(db, ticket.id), db)
            if result.success:
                ticket.hold_reminded_at = now
                reminded += 1
            else:
                # 不落 hold_reminded_at：下一轮重试，避免一次网络抖动永久吞掉提醒。
                logger.warning(
                    "暂缓预计恢复提醒发送失败，下轮重试：ticket_id=%s reason=%s",
                    ticket.id, result.error_message,
                )
        await db.commit()

    if reminded:
        logger.info("暂缓预计恢复时间提醒：%d 条", reminded)
    return {"hold_expiry_reminded": reminded}


async def _scan_loop():
    """后台循环：每分钟扫描一次。"""
    logger.info("SLA 扫描引擎已启动，间隔 %ds", SCAN_INTERVAL_SECONDS)
    while True:
        try:
            await scan_sla_breaches()
        except Exception as e:
            logger.exception("SLA 扫描异常: %s", e)
        try:
            await scan_hold_expiries()
        except Exception as e:
            logger.exception("暂缓提醒扫描异常: %s", e)
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
