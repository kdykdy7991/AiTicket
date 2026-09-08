"""Articles router — list and create communication records."""

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.exceptions import NotFoundError
from app.models.ticket import Article, ArticleAttachment, Ticket, TicketStateLog
from app.models.user import User
from app.services.notification import remind_handler
from app.services.state_machine import TERMINAL_STATES, validate_transition

router = APIRouter(tags=["articles"])

# 允许追加的工单状态：已处理之前（不包括已处理），以及退回后补充阶段
ADDITION_ALLOWED_STATES = {"pending", "open", "on_hold", "returned"}
# 允许追加的角色
ADDITION_ALLOWED_ROLES = {"admin", "agent"}
# 可提交处理说明的工单状态（处理人提交即流转到已处理）
REPLY_ALLOWED_STATES = {"open", "on_hold"}
# 允许催办的状态
URGE_ALLOWED_STATES = {"pending", "open", "on_hold"}
# 允许催办的角色（客服团队）
URGE_ALLOWED_ROLES = {"admin", "agent"}
# 催办内容最大长度
URGE_MAX_LENGTH = 200


@router.get("/tickets/{ticket_id}/articles")
async def list_articles(
    ticket_id: int,
    type: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get articles for a ticket."""
    # Verify ticket exists
    ticket = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    if not ticket.scalar_one_or_none():
        raise NotFoundError("工单", ticket_id)

    # 避免与参数名冲突
    article_type = type
    query = (
        select(Article)
        .options(selectinload(Article.sender), selectinload(Article.attachments))
        .where(Article.ticket_id == ticket_id)
        .order_by(Article.created_at.asc())
    )
    if article_type:
        query = query.where(Article.type == article_type)

    result = await db.execute(query)
    articles = result.scalars().all()

    data = []
    for a in articles:
        data.append({
            "id": a.id, "ticket_id": a.ticket_id, "type": a.type,
            "sender_id": a.sender_id,
            "sender_name": a.sender.name if a.sender else None,
            "subject": a.subject, "body": a.body,
            "state_key": a.state_key,
            "append_reason": a.append_reason,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "updated_at": a.updated_at.isoformat() if a.updated_at else None,
            "attachments": [
                {
                    "id": att.id,
                    "filename": att.filename,
                    "original_filename": att.original_filename,
                    "content_type": att.content_type,
                    "size": att.size,
                    "url": _attachment_url(att.storage_path),
                    "created_at": att.created_at.isoformat() if att.created_at else None,
                }
                for att in a.attachments
            ],
        })
    return {"data": data}


def _attachment_url(storage_path: str) -> str:
    """Return the public URL for a stored attachment."""
    public_path = settings.PUBLIC_UPLOAD_URL.rstrip("/")
    return f"{public_path}/{storage_path}"


async def _save_attachments(
    article_id: int,
    ticket_id: int,
    attachments: list[UploadFile],
) -> list[ArticleAttachment]:
    """Persist uploaded image files and return attachment records."""
    upload_root = Path(settings.UPLOAD_DIR)
    article_dir = upload_root / "articles" / str(ticket_id) / uuid.uuid4().hex
    article_dir.mkdir(parents=True, exist_ok=True)

    records: list[ArticleAttachment] = []
    for upload in attachments:
        if not upload.content_type or not upload.content_type.startswith("image/"):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"仅支持图片文件， got {upload.content_type}",
            )

        content = await upload.read()
        if len(content) > settings.UPLOAD_MAX_SIZE:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"单张图片不能超过 {settings.UPLOAD_MAX_SIZE // 1024 // 1024} MB",
            )

        original = upload.filename or "untitled"
        ext = Path(original).suffix.lower() or ".bin"
        stored_name = f"{uuid.uuid4().hex}{ext}"
        dest = article_dir / stored_name
        dest.write_bytes(content)

        storage_path = str(dest.relative_to(upload_root))
        records.append(
            ArticleAttachment(
                article_id=article_id,
                filename=stored_name,
                original_filename=original,
                content_type=upload.content_type,
                size=len(content),
                storage_path=storage_path,
            )
        )
    return records


@router.post("/tickets/{ticket_id}/articles", status_code=status.HTTP_201_CREATED)
async def create_article(
    ticket_id: int,
    type: Annotated[str, Form()],
    body: Annotated[str, Form()] = "",
    append_reason: Annotated[str | None, Form()] = None,
    attachments: list[UploadFile] = File(default=[]),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Add an article (reply / addition / reminder) to a ticket."""
    ticket_result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = ticket_result.scalar_one_or_none()
    if not ticket:
        raise NotFoundError("工单", ticket_id)

    # 终态工单不再接受任何沟通记录
    if ticket.state in TERMINAL_STATES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="工单已结束，无法提交处理说明、补充或催办"
        )

    # internal_note type has been removed
    if type == "internal_note":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="内部备注功能已下线"
        )

    # 处理说明：只有当前处理人可提交，且工单须处于处理中/暂缓
    # 提交后自动流转到「已处理(resolved)」，处理说明挂在对应 resolved 节点下
    reply_log = None
    if type == "reply":
        if ticket.owner_id is None or user.id != ticket.owner_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="仅当前处理人可提交处理说明"
            )
        if ticket.state not in REPLY_ALLOWED_STATES:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="工单当前状态不可提交处理说明"
            )

    # 追加：仅指定角色 + 指定状态
    if type == "addition":
        if user.role not in ADDITION_ALLOWED_ROLES:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="仅客服人员和管理员可补充"
            )
        if ticket.state not in ADDITION_ALLOWED_STATES:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="仅在已处理之前的状态可补充"
            )

    # 催办：仅客服团队 + 非终态前三种状态 + 整个生命周期只能催办一次
    if type == "reminder":
        if user.role not in URGE_ALLOWED_ROLES:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="仅客服团队可催办"
            )
        if ticket.state not in URGE_ALLOWED_STATES:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="当前状态不可催办"
            )
        if ticket.urged_at is not None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="该工单已催办"
            )

    # Validate type-specific rules
    if type == "addition" and not append_reason:
        raise HTTPException(422, detail="补充类型必须填写补充原因")

    if type == "reminder":
        content = body.strip() if body else ""
        if not content:
            raise HTTPException(422, detail="催办内容不能为空")
        if len(content) > URGE_MAX_LENGTH:
            raise HTTPException(422, detail=f"催办内容最多 {URGE_MAX_LENGTH} 字")

    if type == "reply":
        old_state = ticket.state
        validate_transition(old_state, "resolved")
        now = datetime.now(timezone.utc)

        # 计算上一状态停留时长
        last_log = await db.execute(
            select(TicketStateLog)
            .where(TicketStateLog.ticket_id == ticket_id)
            .order_by(TicketStateLog.created_at.desc()).limit(1)
        )
        last = last_log.scalar_one_or_none()
        duration = int((now - last.created_at).total_seconds() / 60) if last else None

        # 先创建状态日志并 flush，拿到 log.id 作为处理说明的 state_key
        # 人员快照：reply 时刻工单上的创建者/对接人/处理人
        reply_log = TicketStateLog(
            ticket_id=ticket.id, from_state=old_state, to_state="resolved",
            operator_id=user.id, reason=None, duration_minutes=duration,
            creator_id_snapshot=ticket.creator_id,
            dispatcher_id_snapshot=ticket.dispatcher_id,
            owner_id_snapshot=ticket.owner_id,
        )
        db.add(reply_log)
        await db.flush()
        await db.refresh(reply_log)

        # 同一 resolved 节点下只能有一条处理说明
        if last and last.to_state == "resolved":
            existing = await db.execute(
                select(Article).where(
                    Article.ticket_id == ticket_id,
                    Article.type == "reply",
                    Article.state_key == str(last.id),
                )
            )
            if existing.scalar_one_or_none():
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    detail="当前状态下已存在处理说明"
                )

        ticket.state = "resolved"
        ticket.solved_at = now
        ticket.resolved = True
        if ticket.solution_deadline and now > ticket.solution_deadline:
            ticket.sla_solution_breached = True

    article = Article(
        ticket_id=ticket_id, type=type, sender_id=user.id,
        body=body,
        state_key=str(reply_log.id) if reply_log else (ticket.state if type == "reminder" else None),
        append_reason=append_reason if type == "addition" else None,
    )
    db.add(article)
    await db.flush()
    await db.refresh(article)

    # 保存附件（仅追加类型允许上传截图）
    saved_attachments: list[ArticleAttachment] = []
    if type == "addition" and attachments:
        saved_attachments = await _save_attachments(article.id, ticket_id, attachments)
        for att in saved_attachments:
            db.add(att)
        await db.flush()

    # 催办副作用：记录催办时间/催办人，并触发通知扩展点
    if type == "reminder":
        now = datetime.now(timezone.utc)
        ticket.urged_at = now
        ticket.urged_by_id = user.id
        await db.flush()
        await remind_handler(ticket, article, db)

    # 追加信息副作用：标记工单已有追加信息
    if type == "addition":
        ticket.has_addition = True

    # 追加/回复/催办后同步更新工单 updated_at，让列表和详情时间一致
    ticket.updated_at = datetime.now(timezone.utc)
    await db.flush()

    # Reload with sender and attachments
    result = await db.execute(
        select(Article)
        .options(selectinload(Article.sender), selectinload(Article.attachments))
        .where(Article.id == article.id)
    )
    article = result.scalar_one()

    return {
        "data": {
            "id": article.id, "ticket_id": article.ticket_id, "type": article.type,
            "sender_id": article.sender_id,
            "sender_name": article.sender.name if article.sender else None,
            "body": article.body,
            "state_key": article.state_key,
            "append_reason": article.append_reason,
            "created_at": article.created_at.isoformat() if article.created_at else None,
            "updated_at": article.updated_at.isoformat() if article.updated_at else None,
            "attachments": [
                {
                    "id": att.id,
                    "filename": att.filename,
                    "original_filename": att.original_filename,
                    "content_type": att.content_type,
                    "size": att.size,
                    "url": _attachment_url(att.storage_path),
                    "created_at": att.created_at.isoformat() if att.created_at else None,
                }
                for att in article.attachments
            ],
        }
    }
