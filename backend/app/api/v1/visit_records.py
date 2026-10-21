"""独立来访记录：查询、登记和修订，不创建工单。"""

import csv
import io
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.models.user import User
from app.models.visit_record import VisitRecord


router = APIRouter(prefix="/visit-records", tags=["visit-records"])

FIELD_KEYS = {
    "source_order", "customer_source", "gender", "customer_type", "company_name",
    "valid_contact", "priority", "request", "department", "liaison", "handler",
    "handling_detail", "callback_status", "callback_time", "callback_detail",
    "returned", "closed", "closed_at", "satisfaction", "notes",
}

CSV_FIELDS = [
    ("source_order", "原表序号"), ("customer_source", "客户来源"), ("gender", "称谓"),
    ("customer_type", "客户分类"), ("company_name", "公司名称"),
    ("valid_contact", "是否有效电话"), ("priority", "事件等级"),
    ("request", "客户诉求"), ("department", "对接部门"), ("liaison", "对接人"),
    ("handler", "处理人"), ("handling_detail", "处理详情"),
    ("callback_status", "是否回访"), ("callback_time", "回访时间"),
    ("callback_detail", "回访详情"), ("returned", "是否退回处理"),
    ("closed", "是否闭环"), ("closed_at", "闭环时间"),
    ("satisfaction", "满意度"), ("notes", "备注"),
]


def _conditions(keyword: str | None, channel: str | None, registered_ticket: bool | None):
    conditions = []
    if keyword:
        term = f"%{keyword.strip()}%"
        conditions.append(or_(VisitRecord.contact_number.ilike(term),
                              VisitRecord.customer_name.ilike(term),
                              VisitRecord.category_l1.ilike(term),
                              VisitRecord.category_l2.ilike(term)))
    if channel:
        conditions.append(VisitRecord.channel == channel)
    if registered_ticket is not None:
        conditions.append(VisitRecord.registered_ticket == registered_ticket)
    return conditions


class VisitPayload(BaseModel):
    contact_at: datetime
    contact_number: str | None = Field(None, max_length=100)
    customer_name: str | None = Field(None, max_length=100)
    service_agent: str | None = Field(None, max_length=100)
    channel: str = Field("400客服热线", max_length=40)
    category_l1: str | None = Field(None, max_length=100)
    category_l2: str | None = Field(None, max_length=100)
    registered_ticket: bool | None = None
    fields: dict[str, str | None] = Field(default_factory=dict)


def _serialize(record: VisitRecord) -> dict:
    return {
        "id": record.id,
        "source_sheet": record.source_sheet,
        "source_row": record.source_row,
        "contact_at": record.contact_at.isoformat(),
        "contact_number": record.contact_number,
        "customer_name": record.customer_name,
        "service_agent": record.service_agent,
        "channel": record.channel,
        "category_l1": record.category_l1,
        "category_l2": record.category_l2,
        "registered_ticket": record.registered_ticket,
        "fields": record.fields or {},
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


def _apply(record: VisitRecord, payload: VisitPayload) -> None:
    if payload.contact_at.tzinfo is None:
        raise HTTPException(422, detail="联系时间必须包含时区")
    if payload.channel not in {"400客服热线", "在线客服"}:
        raise HTTPException(422, detail="来访渠道无效")
    unknown = set(payload.fields) - FIELD_KEYS
    if unknown:
        raise HTTPException(422, detail=f"未知字段：{', '.join(sorted(unknown))}")
    for key in ("contact_at", "contact_number", "customer_name", "service_agent",
                "channel", "category_l1", "category_l2", "registered_ticket"):
        setattr(record, key, getattr(payload, key))
    record.fields = {key: value for key, value in payload.fields.items() if value not in (None, "")}


@router.get("")
async def list_visits(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = None,
    channel: str | None = None,
    registered_ticket: bool | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conditions = _conditions(keyword, channel, registered_ticket)
    total = (await db.execute(select(func.count()).select_from(VisitRecord).where(*conditions))).scalar_one()
    items = (await db.execute(select(VisitRecord).where(*conditions)
                              .order_by(VisitRecord.contact_at.desc(), VisitRecord.id.desc())
                              .offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return {"data": [_serialize(item) for item in items],
            "pagination": {"page": page, "page_size": page_size, "total": total}}


@router.get("/export")
async def export_visits(
    keyword: str | None = None,
    channel: str | None = None,
    registered_ticket: bool | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    records = (await db.execute(select(VisitRecord).where(
        *_conditions(keyword, channel, registered_ticket)
    ).order_by(VisitRecord.contact_at.desc(), VisitRecord.id.desc()))).scalars().all()
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(["原始Sheet", "原始行号", "渠道", "联系时间", "联系号码", "姓名", "接待客服",
                     "一级分类", "二级分类", *[label for _, label in CSV_FIELDS]])
    local_tz = timezone(timedelta(hours=8))
    for record in records:
        writer.writerow([
            record.source_sheet or "", record.source_row or "", record.channel,
            record.contact_at.astimezone(local_tz).strftime("%Y-%m-%d %H:%M:%S"),
            record.contact_number or "", record.customer_name or "", record.service_agent or "",
            record.category_l1 or "", record.category_l2 or "",
            *[(record.fields or {}).get(key, "") for key, _ in CSV_FIELDS],
        ])
    return StreamingResponse(iter([output.getvalue().encode("utf-8")]), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="visit_records.csv"'})


@router.post("", status_code=201)
async def create_visit(
    payload: VisitPayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "agent")),
):
    record = VisitRecord()
    _apply(record, payload)
    db.add(record)
    await db.flush()
    await db.refresh(record)
    return {"data": _serialize(record)}


@router.put("/{record_id}")
async def update_visit(
    record_id: int,
    payload: VisitPayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "agent")),
):
    record = await db.get(VisitRecord, record_id)
    if record is None:
        raise HTTPException(404, detail="来访记录不存在")
    _apply(record, payload)
    await db.flush()
    await db.refresh(record)
    return {"data": _serialize(record)}
