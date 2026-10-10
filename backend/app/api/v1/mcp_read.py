"""Read-only integration API for the separately deployed MCP service.

The shared tenant token identifies the agent platform, never an end user.
Only these GET routes accept the internal token; it cannot authorize writes.
"""

import secrets
from datetime import date, datetime, time

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.models.category import TicketCategory
from app.models.ticket import Article, Ticket, TicketStateLog
from app.models.user import User
from app.services.category_utils import build_lineage_index


def require_mcp_internal_token(authorization: str | None = Header(default=None)) -> None:
    configured = settings.MCP_INTERNAL_TOKEN
    if not configured:
        raise HTTPException(503, detail="MCP integration is disabled")
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(token, configured):
        raise HTTPException(401, detail="Invalid MCP integration token")


router = APIRouter(
    prefix="/internal/mcp",
    tags=["mcp-internal"],
    dependencies=[Depends(require_mcp_internal_token)],
    include_in_schema=False,
)


def _ticket_summary(ticket: Ticket) -> dict:
    return {
        "number": ticket.number,
        "state": ticket.state,
        "category": ticket.category.name if ticket.category else None,
        "owner": ticket.owner.name if ticket.owner else None,
        "created_at": ticket.created_at.isoformat(),
    }


@router.get("/tickets/recent")
async def list_recent_tickets(
    limit: int = Query(3, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    """Return the newest submitted tickets in creation-time order."""
    rows = (await db.execute(
        select(Ticket)
        .options(selectinload(Ticket.category), selectinload(Ticket.owner))
        .where(Ticket.is_draft.is_(False), Ticket.number.is_not(None))
        .order_by(Ticket.created_at.desc(), Ticket.id.desc())
        .limit(limit)
    )).scalars().all()
    return {"data": [_ticket_summary(ticket) for ticket in rows]}


@router.get("/tickets/filter")
async def filter_tickets(
    state: str | None = Query(None, max_length=30),
    category_id: int | None = Query(None, ge=1),
    owner_name: str | None = Query(None, min_length=2, max_length=100),
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = Query(1, ge=1, le=100),
    limit: int = Query(10, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    """Filter submitted tickets with bounded pagination and a stable sort."""
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, detail="date_from must not exceed date_to")
    filters = [Ticket.is_draft.is_(False), Ticket.number.is_not(None)]
    if state:
        filters.append(Ticket.state == state)
    if category_id:
        lineage_index = await build_lineage_index(db)
        category_ids = [
            candidate_id for candidate_id, lineage in lineage_index.items()
            if any(category.id == category_id for category in lineage.path)
        ]
        filters.append(Ticket.category_id.in_(category_ids))
    if owner_name:
        filters.append(Ticket.owner.has(User.name.ilike(f"%{owner_name}%")))
    if date_from:
        filters.append(Ticket.created_at >= datetime.combine(date_from, time.min))
    if date_to:
        filters.append(Ticket.created_at <= datetime.combine(date_to, time.max))
    total = (await db.execute(select(func.count(Ticket.id)).where(*filters))).scalar_one()
    rows = (await db.execute(
        select(Ticket)
        .options(selectinload(Ticket.category), selectinload(Ticket.owner))
        .where(*filters)
        .order_by(Ticket.created_at.desc(), Ticket.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )).scalars().all()
    return {"data": {"total": total, "page": page, "items": [_ticket_summary(ticket) for ticket in rows]}}


@router.get("/tickets")
async def search_tickets(
    keyword: str = Query(..., min_length=2, max_length=100),
    limit: int = Query(10, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    """Search non-draft tickets; return a bounded, concise result set."""
    pattern = f"%{keyword}%"
    rows = (await db.execute(
        select(Ticket)
        .options(selectinload(Ticket.category), selectinload(Ticket.owner))
        .where(
            Ticket.is_draft.is_(False),
            or_(
                Ticket.number.ilike(pattern),
                Ticket.description.ilike(pattern),
                Ticket.customer_name.ilike(pattern),
                Ticket.customer_phone.ilike(pattern),
            ),
        )
        .order_by(Ticket.created_at.desc(), Ticket.id.desc())
        .limit(limit)
    )).scalars().all()
    return {"data": [_ticket_summary(ticket) for ticket in rows]}


@router.get("/tickets/{number}")
async def get_ticket(number: str, db: AsyncSession = Depends(get_db)):
    ticket = (await db.execute(
        select(Ticket)
        .options(
            selectinload(Ticket.category), selectinload(Ticket.creator),
            selectinload(Ticket.owner), selectinload(Ticket.dispatcher),
            selectinload(Ticket.skill_group),
        )
        .where(Ticket.number == number, Ticket.is_draft.is_(False))
    )).scalar_one_or_none()
    if ticket is None:
        raise HTTPException(404, detail="Ticket not found")

    lineage = (await build_lineage_index(db)).get(ticket.category_id)
    logs = (await db.execute(
        select(TicketStateLog, User.name)
        .join(User, User.id == TicketStateLog.operator_id)
        .where(TicketStateLog.ticket_id == ticket.id)
        .order_by(TicketStateLog.created_at, TicketStateLog.id)
    )).all()
    replies = (await db.execute(
        select(Article, User.name)
        .join(User, User.id == Article.sender_id)
        .where(Article.ticket_id == ticket.id, Article.type == "reply")
        .order_by(Article.created_at, Article.id)
    )).all()
    return {"data": {
        "number": ticket.number,
        "state": ticket.state,
        "description": ticket.description,
        "category_path": " / ".join(c.name for c in lineage.path) if lineage else None,
        "customer_name": ticket.customer_name,
        "customer_phone": ticket.customer_phone,
        "creator": ticket.creator.name if ticket.creator else None,
        "dispatcher": ticket.dispatcher.name if ticket.dispatcher else None,
        "owner": ticket.owner.name if ticket.owner else None,
        "department": ticket.skill_group.name if ticket.skill_group else None,
        "created_at": ticket.created_at.isoformat(),
        "updated_at": ticket.updated_at.isoformat(),
        "has_returned": ticket.has_returned,
        "timeline": [
            {
                "action": log.action_type,
                "from_state": log.from_state,
                "to_state": log.to_state,
                "operator": operator_name,
                "reason": log.reason,
                "at": log.created_at.isoformat(),
            }
            for log, operator_name in logs
        ],
        "processing_notes": [
            {"sender": sender_name, "body": article.body, "at": article.created_at.isoformat()}
            for article, sender_name in replies
        ],
    }}


@router.get("/categories")
async def get_categories(db: AsyncSession = Depends(get_db)):
    categories = (await db.execute(
        select(TicketCategory)
        .where(TicketCategory.is_active.is_(True))
        .order_by(TicketCategory.sort_order, TicketCategory.id)
    )).scalars().all()
    by_id = {category.id: category for category in categories}
    nodes = {
        category.id: {"id": category.id, "name": category.name, "children": []}
        for category in categories
    }
    roots = []
    for category in categories:
        if category.parent_id in by_id:
            nodes[category.parent_id]["children"].append(nodes[category.id])
        else:
            roots.append(nodes[category.id])
    return {"data": roots}
