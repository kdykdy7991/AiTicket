"""Category-based resolution SLA and immutable per-attempt timing history."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import TicketCategory
from app.models.sla import SLAPolicy, SLARound
from app.models.ticket import Ticket

ASSURANCE_VARIANTS = {"p1_urgent", "p2_high", "p3_normal", "p4_enterprise"}
COMPLAINT_VARIANTS = {"一般", "重要", "重大"}
COMPLAINT_ROOT_NAMES = {"投诉", "服务投诉", "投诉类"}


async def root_category(db: AsyncSession, category_id: int | None) -> TicketCategory | None:
    if category_id is None:
        return None
    category = await db.get(TicketCategory, category_id)
    seen: set[int] = set()
    while category is not None and category.parent_id is not None:
        if category.id in seen:
            return None
        seen.add(category.id)
        category = await db.get(TicketCategory, category.parent_id)
    return category


def valid_variant(root_name: str, variant: str) -> bool:
    if root_name == "业务保障":
        return variant in ASSURANCE_VARIANTS
    if root_name in COMPLAINT_ROOT_NAMES:
        return variant in COMPLAINT_VARIANTS
    return variant == "default"


async def matching_policy(
    db: AsyncSession, *, category_id: int | None, priority: str,
    complaint_level: str | None, is_opportunity: bool | None,
    is_instant: bool = False,
) -> SLAPolicy | None:
    if is_opportunity or is_instant:
        return None
    root = await root_category(db, category_id)
    if root is None:
        return None
    variant = priority if root.name == "业务保障" else (
        complaint_level if root.name in COMPLAINT_ROOT_NAMES else "default"
    )
    if not variant or not valid_variant(root.name, variant):
        return None
    return (await db.execute(select(SLAPolicy).where(
        SLAPolicy.category_id == root.id, SLAPolicy.variant == variant,
    ))).scalar_one_or_none()


async def start_round(db: AsyncSession, ticket: Ticket, *, started_at: datetime | None = None,
                      is_instant: bool = False) -> SLARound | None:
    policy = await matching_policy(
        db, category_id=ticket.category_id, priority=ticket.priority,
        complaint_level=ticket.complaint_level, is_opportunity=ticket.is_opportunity,
        is_instant=is_instant,
    )
    if policy is None:
        ticket.solution_deadline = None
        return None
    previous = (await db.execute(select(SLARound).where(SLARound.ticket_id == ticket.id)
                                 .order_by(SLARound.sequence.desc()).limit(1))).scalar_one_or_none()
    if previous and previous.status == "running":
        return previous
    started = started_at or datetime.now(timezone.utc)
    round_ = SLARound(
        ticket_id=ticket.id, sequence=(previous.sequence + 1 if previous else 1),
        started_at=started, deadline_at=started + timedelta(minutes=policy.solution_minutes),
        status="running", breached=False,
    )
    db.add(round_)
    ticket.solution_deadline = round_.deadline_at
    await db.flush()
    return round_


async def finish_round(db: AsyncSession, ticket: Ticket, *, status: str,
                       ended_at: datetime | None = None) -> None:
    current = (await db.execute(select(SLARound).where(
        SLARound.ticket_id == ticket.id, SLARound.status == "running",
    ).order_by(SLARound.sequence.desc()).limit(1))).scalar_one_or_none()
    if current is None:
        if ticket.solution_deadline and (ended_at or datetime.now(timezone.utc)) > ticket.solution_deadline:
            ticket.sla_solution_breached = True
        return
    ended = ended_at or datetime.now(timezone.utc)
    current.ended_at = ended
    current.status = status
    if ended > current.deadline_at:
        current.breached = True
        ticket.sla_solution_breached = True


async def replace_running_deadline(db: AsyncSession, ticket: Ticket) -> None:
    """Re-evaluate an active round without resetting its original start time."""
    current = (await db.execute(select(SLARound).where(
        SLARound.ticket_id == ticket.id, SLARound.status == "running",
    ).order_by(SLARound.sequence.desc()).limit(1))).scalar_one_or_none()
    if current is None:
        if ticket.solution_deadline is None and ticket.solved_at is None:
            await start_round(db, ticket, started_at=ticket.created_at)
        return
    policy = await matching_policy(
        db, category_id=ticket.category_id, priority=ticket.priority,
        complaint_level=ticket.complaint_level, is_opportunity=ticket.is_opportunity,
    )
    if policy is None:
        current.status = "cancelled"
        current.ended_at = datetime.now(timezone.utc)
        ticket.solution_deadline = None
        return
    current.deadline_at = current.started_at + timedelta(minutes=policy.solution_minutes)
    ticket.solution_deadline = current.deadline_at
