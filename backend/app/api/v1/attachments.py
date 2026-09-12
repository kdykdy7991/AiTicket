"""POC 工单附件：创建阶段与后续阶段上传、鉴权下载。

存储目录不对内公开，下载必须经过工单查看权限校验。
存储文件名随机化，原始文件名只作为元数据保存。
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.exceptions import ForbiddenError, NotFoundError
from app.domain.poc_workflow import BusinessRole, TERMINAL_STATES
from app.models.ticket import Ticket, TicketAttachment
from app.models.user import User
from app.schemas.ticket import TicketAttachmentOut
from app.services.poc_workflow import can_view, ensure_can_view, responsible_role, responsible_user_id

router = APIRouter(tags=["attachments"])

TERMINAL_VALUES = {state.value for state in TERMINAL_STATES}

#: 允许的扩展名 -> 允许多个 MIME 前缀
ALLOWED_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "jpg": ("image/jpeg",),
    "jpeg": ("image/jpeg",),
    "png": ("image/png",),
    "webp": ("image/webp",),
    "pdf": ("application/pdf",),
    "doc": ("application/msword",),
    "docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
    "xls": ("application/vnd.ms-excel",),
    "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",),
    "txt": ("text/plain",),
    "log": ("text/plain",),
    "zip": ("application/zip", "application/x-zip-compressed"),
}

WILDCARD_MIME = "application/octet-stream"


def can_attach(ticket: Ticket, actor: User) -> bool:
    """当前节点是否允许该用户上传材料。"""
    if ticket.state in TERMINAL_VALUES:
        return False
    if actor.has_role(BusinessRole.ADMIN):
        return True
    if actor.has_role(BusinessRole.PRESALES) and ticket.creator_id == actor.id:
        # 创建人可以在待审批/退回阶段补充现场材料（含草稿）
        return True
    uid = responsible_user_id(ticket)
    if uid is not None:
        return actor.id == uid
    role = responsible_role(ticket)
    if role is not None:
        return actor.has_role(role)
    return False


def _validate_file(upload: UploadFile, content: bytes) -> str:
    original = upload.filename or "untitled"
    ext = Path(original).suffix.lower().lstrip(".")
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            422,
            detail=f"不支持的文件类型：{ext or '(无扩展名)'}，"
            f"允许 {'/'.join(sorted(ALLOWED_EXTENSIONS))}",
        )
    if not content:
        raise HTTPException(422, detail=f"文件 {original} 内容为空")
    if len(content) > settings.UPLOAD_MAX_SIZE:
        raise HTTPException(
            413,
            detail=f"单个文件不能超过 {settings.UPLOAD_MAX_SIZE // 1024 // 1024} MB",
        )
    declared = (upload.content_type or "").split(";")[0].strip().lower()
    allowed = ALLOWED_EXTENSIONS[ext]
    if declared and declared != WILDCARD_MIME and not declared.startswith(allowed):
        raise HTTPException(
            422,
            detail=f"文件 {original} 的 MIME 类型与扩展名不匹配（{declared}）",
        )
    return ext


def _attachment_out(att: TicketAttachment) -> TicketAttachmentOut:
    return TicketAttachmentOut(
        id=att.id,
        ticket_id=att.ticket_id,
        original_filename=att.original_filename,
        content_type=att.content_type,
        size=att.size,
        stage=att.stage,
        uploader_id=att.uploader_id,
        uploader_name=att.uploader.name if att.uploader else None,
        download_url=f"/api/v1/attachments/{att.id}/download",
        created_at=att.created_at,
    )


@router.post(
    "/tickets/{ticket_id}/attachments",
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachments(
    ticket_id: int,
    files: list[UploadFile] = File(..., description="现场照片 / 日志 / 报告等"),
    stage: str | None = Form(None, description="留空时按工单当前状态记录"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ticket = (await db.execute(select(Ticket).where(Ticket.id == ticket_id))).scalar_one_or_none()
    if ticket is None or ticket.legacy_state is not None:
        raise NotFoundError("问题", ticket_id)
    ensure_can_view(ticket, user)
    if not can_attach(ticket, user):
        raise ForbiddenError("当前节点你无权上传附件")
    if stage is not None and stage != ticket.state:
        raise HTTPException(422, detail="stage 必须与工单当前状态一致")

    upload_root = Path(settings.UPLOAD_DIR)
    target_dir = upload_root / "tickets" / str(ticket.id)
    target_dir.mkdir(parents=True, exist_ok=True)

    records: list[TicketAttachment] = []
    for upload in files:
        content = await upload.read()
        ext = _validate_file(upload, content)
        stored_name = f"{uuid.uuid4().hex}.{ext}"
        dest = target_dir / stored_name
        dest.write_bytes(content)
        record = TicketAttachment(
            ticket_id=ticket.id,
            filename=stored_name,
            original_filename=(upload.filename or "untitled")[:500],
            content_type=(
                (upload.content_type or WILDCARD_MIME).split(";")[0].strip()
                or WILDCARD_MIME
            ),
            size=len(content),
            storage_path=str(dest.relative_to(upload_root)),
            stage=ticket.state,
            uploader_id=user.id,
        )
        db.add(record)
        records.append(record)

    await db.flush()
    for record in records:
        await db.refresh(record)
    await db.commit()
    return {"data": [_attachment_out(r).model_dump() for r in records]}


@router.get("/attachments/{attachment_id}/download")
async def download_attachment(
    attachment_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    attachment = await db.get(TicketAttachment, attachment_id)
    if attachment is None:
        raise NotFoundError("附件", attachment_id)

    if attachment.ticket_id is None:
        # 历史客服附件没有工单归属，仅管理员可取
        if not user.has_role(BusinessRole.ADMIN):
            raise ForbiddenError("无权下载该附件")
    else:
        ticket = await db.get(Ticket, attachment.ticket_id)
        if ticket is None or ticket.legacy_state is not None:
            raise NotFoundError("附件", attachment_id)
        if not can_view(ticket, user):
            raise ForbiddenError("无权下载该附件")

    path = Path(settings.UPLOAD_DIR) / attachment.storage_path
    if not path.is_file():
        raise NotFoundError("附件文件", attachment_id)
    return FileResponse(
        path,
        media_type=attachment.content_type or WILDCARD_MIME,
        filename=attachment.original_filename,
    )
